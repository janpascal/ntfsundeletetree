# ntfsundeletetree
Tool based on ntfsundelete from ntfs-3g to recursively undelete files and directoryies from NTFS

Usage:
1. Patch `ntfs-3g` using the supplies patch file. This makes `ntfsundelete` report the parent 
   inode (next to the parent name) of each discovered deleted file in the output of `ntfsundelete --scan`.
2. Run `ntfsundeletetree.py` using Python 3.7 or later.
```
usage: ntfsundeletetree [-h] [-r ROOT_INODE] [-d FROM_DATE] image outdir

Recursively undelete deleted files and directory from an NTFS partition or image

positional arguments:
  image                 NTFS partition or image file
  outdir                Output directory. Must not exist

optional arguments:
  -h, --help            show this help message and exit
  -r ROOT_INODE, --root_inode ROOT_INODE
                        Root directory inode. Leave empty to undelete all trees
  -d FROM_DATE, --from-date FROM_DATE
                        Date limit for files in ISO format. Older files will be skipped
```
