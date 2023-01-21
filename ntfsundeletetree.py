#!/usr/bin/env python3

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import os
import os.path
import re
import subprocess
import sys

NTFSUNDELETE="/sbin/ntfsundelete"

class FileType(Enum):
    DIRECTORY = 'Directory'
    FILE = 'File'

@dataclass
class FileRecord:
    inode: int
    filetype: FileType
    name: str
    parent: int
    recoverable: int # percentage
    latest_timestamp: datetime

@dataclass
class TreeNode:
    record: FileRecord
    children: list #: list[int] = field(default_factory=list)

@dataclass
class Tree:
    roots: list #: list[int]
    index: dict #: dict[int, TreeNode]

def handle_record(inode, filetype, filename, parent):
    print(f"{inode} {filetype} {filename} {parent}")

# Map inodeis to FileType records
def analyse(image):
    records = {}

    inode_pattern = re.compile(r"MFT Record ([\d]*)")
    type_pattern = re.compile(r"Type: (File|Directory)")
    filename_pattern = re.compile(r"Filename: \((\d*)\) (.*)")
    parent_pattern = re.compile(r"Parent inode: ([\d]*)")
    recoverable_pattern = re.compile(r"File is ([\d]*)% recoverable")
    timestamp_pattern = re.compile(r"Date(| C| A| M| R): (\d\d\d\d-\d\d-\d\d \d\d:\d\d)")

    print(f"Executing {NTFSUNDELETE} --verbose --parent {image} ...")
    scan_result = subprocess.run(
        [
            NTFSUNDELETE,
            "--verbose",
            "--parent",
            image
        ], 
        capture_output=True,
        text=True)

    if scan_result.returncode != 0:
        print(scan_result.stdout)
        print(scan_result.stderr)
        return

    print(f"Analysing result...")
    stdout = scan_result.stdout

    inode = None
    filetype = None
    filename = None
    parent = None
    recoverable = None
    latest_timestamp = datetime(1970,1,1)

    for line in stdout.splitlines():
        #print(line)
        if line.startswith("____"):
            #handle_record(inode, filetype, filename, parent)
            if not (filetype == FileType.FILE and filename is None and parent is None):
                if filename is None:
                    filename = "<unknown>"
                record = FileRecord(inode, filetype, filename, parent,
                        recoverable, latest_timestamp)
                records[inode] = record
            inode = None
            filetype = None
            filename = None
            parent = None
            recoverable = None
            latest_timestamp = datetime(1970,1,1)
            continue

        m = inode_pattern.match(line)
        if m is not None:
            inode = int(m.group(1))
            continue

        m = type_pattern.match(line)
        if m is not None:
            filetype = FileType(m.group(1))
            continue

        m = filename_pattern.match(line)
        if m is not None:
            index = int(m.group(1))
            if filename is None or len(m.group(2)) > len(filename):
                filename = m.group(2)
            continue

        m = parent_pattern.match(line)
        if m is not None:
            parent = int(m.group(1))
            continue

        m = recoverable_pattern.match(line)
        if m is not None:
            recoverable = int(m.group(1))
            continue

        m = timestamp_pattern.match(line)
        if m is not None:
            #print(f"Timestamp: {m.group(2)}")
            timestamp = datetime.strptime(m.group(2), "%Y-%m-%d %H:%M")
            if timestamp > latest_timestamp:
                latest_timestamp = timestamp
                #print(f"Latest Timestamp: {latest_timestamp}")
            continue

    return records

def create_tree(records):
    roots = [] # inodes
    index = {} # inode -> TreeNode
    for record in list(records.values()):
    #for record in reversed(list(records.values())):
        #print(f"Examining {record.inode} ({record.name})")
        print(f"Examining {record}")
        if record.inode in index:
            # Already handled
            continue

        print(f"    Creating node {record.inode}")
        # Add node to tree
        node = TreeNode(record, [])
        index[record.inode] = node

        # If no parent, it's a root
        # Walk up until finding a known parent or root, add nodes to index on the way

        while record is not None:
            # print(f"    Current record: {record}")
            parent_inode = record.parent
            if parent_inode is None:
                print(f"    Current record is root {record.inode}")
                if record.inode not in roots:
                    roots.append(record.inode)
                break
            
            if parent_inode not in records:
                print(f"    Parent record is new root {parent_inode}")
                parent_record = FileRecord(parent_inode, FileType.DIRECTORY,
                        str(parent_inode), None,
                        True, record.latest_timestamp)
                records[parent_inode] = parent_record
            else:
                parent_record = records[parent_inode]

            # print(f"    Parent record: {parent_record}")

            if parent_inode not in index:
                print(f"    Creating node {parent_inode} with child {record.inode}")
                parent_node = TreeNode(parent_record, [record.inode])
                index[parent_inode] = parent_node
            else:
                parent_node = index[parent_inode]
                if record.inode not in parent_node.children:
                    parent_node.children.append(record.inode)

            # print(f"    Parent node: {parent_inode}")

            record = parent_record
            node = parent_node

    return Tree(roots, index)

def print_tree(tree):
    def print_node(tree, node, indent = 0):
        print(" "*indent + str(node.record.inode) + ": " + str(node.record.name))
        for c in node.children:
            print_node(tree, tree.index[c], indent+2)

    for r in tree.roots:
        print_node(tree, tree.index[r], 0)

def uniquefy_path(path):
    initial_path = path
    index = 1
    while os.path.exists(path):
        path = f"{initial_path}.{index}"
        index += 1

    if index > 1:
        print(f"{initial_path} -> {path}")

    return path


def recursive_undelete(image, tree, node, output_dir, from_date):
    path = os.path.join(output_dir, node.record.name)
    path = uniquefy_path(path)

    inode = node.record.inode

    if node.record.filetype == FileType.DIRECTORY:
        if len(node.children) == 0:
            print(f"Skipping empty directory {path} ({inode})")
            return

        print(f"{inode} Creating directory {path}")
        os.makedirs(path)
        timestamp = ( node.record.latest_timestamp -  datetime(1970, 1, 1) ) / timedelta(seconds=1)
        print(f"    Setting directory timestamp to {timestamp}")
        os.utime(path, times=(timestamp, timestamp))
        for i in node.children:
            child = tree.index[i]
            recursive_undelete(image, tree, child, path, from_date)
    elif node.record.filetype == FileType.FILE:
        if node.record.recoverable is None or node.record.recoverable < 100:
            print(f"Skipping {path} ({inode}), only {node.record.recoverable}% recoverable")
            return

        if from_date is not None and node.record.latest_timestamp < from_date:
            print(f"Skipping {path} ({inode}), too old ({node.record.latest_timestamp})")
            return

        print(f"{inode} Writing {path}")
        undelete_result = subprocess.run(
            [
                NTFSUNDELETE,
                "--truncate", 
                "--undelete", 
                "--inodes", str(node.record.inode), 
                "--output", path, 
                image
            ],
            capture_output = True,
            text = True
        )
        if undelete_result.returncode != 0:
            print(f"Undeleting inode {node.record.inode}: exit code {undelete_result.returncode}")
            print(undelete_result.stdout)
            print(undelete_result.stderr)
            return

        # ntfsundelete sometime creates separate ":Zone.Identifier" files, 
        # instead of secondary data streams. Remove them.
        zone_identifier = path + ":Zone.Identifier"
        if os.path.exists(zone_identifier):
            os.remove(zone_identifier)


def undelete(image, root_inode, root_output, from_date):
    if os.path.exists(root_output):
        print(f"{root_output} already exists, bailing out")
        sys.exit(-1)

    os.makedirs(root_output)

    records = analyse(image)
    #print(records)

    tree = create_tree(records)
    print(f"Roots: {tree.roots}")
    print_tree(tree)

    if root_inode is None:
        for root in tree.roots:
            node = tree.index[root]
            recursive_undelete(image, tree, node, root_output, from_date)
    else:
        if root_inode not in tree.index:
            print(f"Unknown inode {root_inode}")

        node = tree.index[root_inode]
        recursive_undelete(image, tree, node, root_output, from_date)

def main():
    parser = argparse.ArgumentParser(
        prog='ntfsundeletetree',
        description = 'Recursively undelete deleted files and directory from an NTFS partition or image'
    )
    parser.add_argument('image', help="NTFS partition or image file")
    parser.add_argument('outdir', help="Output directory. Must not exist")
    parser.add_argument('-r', '--root_inode', default=None, type=int, help="Root directory inode. Leave empty to undelete all trees")
    parser.add_argument('-d', '--from-date', default=None, type=datetime.fromisoformat, help="Date limit for files in ISO format. Older files will be skipped") 

    args = parser.parse_args()


    print(f"Undeleting file and directory trees from {args.image} to {args.outdir} from root inode {args.root_inode}, starting with {args.from_date}")

    undelete(args.image, args.root_inode, args.outdir, args.from_date)

if __name__ == "__main__":
    main()
