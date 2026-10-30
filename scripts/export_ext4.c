/* Export allocated, reachable ext4 files to a PAX tar, without mounting the image.
 * Build with libext2fs, libcom_err and libarchive.
 * Reads the input image only. Never copies free blocks, journal or inode slack.
 */
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <sys/stat.h>
#include <archive.h>
#include <archive_entry.h>
#include <ext2fs/ext2fs.h>

static ext2_filsys fs;
static struct archive *out;
static char **links;
static unsigned char *visited;
static void fail(const char *msg) { fprintf(stderr, "export_ext4: %s\n", msg); exit(1); }
static void ok(errcode_t code) { if (code) { fprintf(stderr,"ext2fs error: %ld\n",(long)code); exit(1); } }
static void arc(int code) { if (code < ARCHIVE_OK) fail(archive_error_string(out)); }
static void emit(ext2_ino_t ino, const char *path);

static int xattr_cb(char *name, char *value, size_t size, void *arg) {
    archive_entry_xattr_add_entry(arg, name, value, size);
    return 0;
}
static int dir_cb(ext2_ino_t parent, int entry, struct ext2_dir_entry *de,
                  int off, int bs, char *buf, void *arg) {
    (void)parent; (void)entry; (void)off; (void)bs; (void)buf;
    if (!de->inode) return 0;
    int n = ext2fs_dirent_name_len(de);
    if ((n==1 && de->name[0]=='.') || (n==2 && !memcmp(de->name,"..",2))) return 0;
    if (n<=0 || memchr(de->name,'/',n) || memchr(de->name,0,n)) fail("invalid directory name");
    char *path;
    if (asprintf(&path,"%s/%.*s",(char*)arg,n,de->name)<0) fail("out of memory");
    emit(de->inode,path);
    free(path);
    return 0;
}
static void emit(ext2_ino_t ino, const char *path) {
    struct ext2_inode inode;
    ok(ext2fs_read_inode(fs,ino,&inode));
    struct archive_entry *e=archive_entry_new();
    if (!e) fail("out of memory");
    archive_entry_set_pathname(e,path);
    archive_entry_set_mode(e,inode.i_mode);
    archive_entry_set_uid(e,inode_uid(inode));
    archive_entry_set_gid(e,inode_gid(inode));
    archive_entry_set_mtime(e,inode.i_mtime,0);
    /* Do not propagate access times or creation metadata from a live device. */
    uint64_t size=EXT2_I_SIZE(&inode);
    int regular=LINUX_S_ISREG(inode.i_mode), directory=LINUX_S_ISDIR(inode.i_mode);
    if (directory && visited[ino]) fail("directory cycle or duplicate");
    if (directory) visited[ino]=1;
    int hardlink=regular && links[ino];
    if (hardlink) archive_entry_set_hardlink(e,links[ino]);
    else if (regular) {
        archive_entry_set_size(e,size);
        if (inode.i_links_count>1) { links[ino]=strdup(path); if(!links[ino])fail("out of memory"); }
    } else if (LINUX_S_ISLNK(inode.i_mode)) {
        if (size>65536) fail("oversized symlink");
        char *target=calloc(1,size+1);
        if (!target) fail("out of memory");
        if (ext2fs_is_fast_symlink(&inode)) memcpy(target,inode.i_block,size);
        else {
            ext2_file_t f; unsigned int got;
            ok(ext2fs_file_open(fs,ino,0,&f));
            ok(ext2fs_file_read(f,target,(unsigned int)size,&got));
            if(got!=size) fail("short symlink read");
            ok(ext2fs_file_close(f));
        }
        archive_entry_set_symlink(e,target); free(target);
    } else if (LINUX_S_ISCHR(inode.i_mode)||LINUX_S_ISBLK(inode.i_mode)) {
        uint32_t dev=inode.i_block[0] ? inode.i_block[0] : inode.i_block[1];
        unsigned major=inode.i_block[0] ? dev>>8 : (dev>>8)&0xfff;
        unsigned minor=inode.i_block[0] ? dev&255 : (dev&255)|((dev>>12)&0xfff00);
        archive_entry_set_rdevmajor(e,major); archive_entry_set_rdevminor(e,minor);
    } else if (!directory && !LINUX_S_ISFIFO(inode.i_mode)) fail("unsupported inode type");
    struct ext2_xattr_handle *h;
    ok(ext2fs_xattrs_open(fs,ino,&h));
    ok(ext2fs_xattrs_read(h));
    ok(ext2fs_xattrs_iterate(h,xattr_cb,e));
    ok(ext2fs_xattrs_close(&h));
    arc(archive_write_header(out,e));
    if (regular && !hardlink) {
        ext2_file_t f; static char buf[1024*1024]; unsigned got;
        ok(ext2fs_file_open(fs,ino,0,&f));
        uint64_t left=size;
        while(left) {
            unsigned want=left>sizeof(buf) ? sizeof(buf) : (unsigned)left;
            ok(ext2fs_file_read(f,buf,want,&got));
            if(got!=want)fail("short file read");
            if(archive_write_data(out,buf,got)!=got) fail("tar data write failed");
            left-=got;
        }
        ok(ext2fs_file_close(f));
    }
    archive_entry_free(e);
    if(directory) ok(ext2fs_dir_iterate2(fs,ino,0,NULL,dir_cb,(void*)path));
}
int main(int argc,char **argv) {
    if(argc!=3) fail("usage: export_ext4 input.img output.tar");
    umask(0077);
    ok(ext2fs_open(argv[1],EXT2_FLAG_64BITS,0,0,unix_io_manager,&fs));
    links=calloc((size_t)fs->super->s_inodes_count+1,sizeof(char*));
    visited=calloc((size_t)fs->super->s_inodes_count+1,1);
    if(!links||!visited)fail("out of memory");
    out=archive_write_new();
    arc(archive_write_set_format_pax(out));
    arc(archive_write_open_filename(out,argv[2]));
    emit(EXT2_ROOT_INO,".");
    arc(archive_write_close(out));
    archive_write_free(out); ext2fs_close(fs);
    return 0;
}
