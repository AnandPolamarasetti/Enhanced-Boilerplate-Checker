import argparse
import datetime
import difflib
import glob
import os
import re
import sys

# Argument parser setup
parser = argparse.ArgumentParser(description="Check and validate file headers against boilerplate standards.")
parser.add_argument(
    "filenames", help="List of files to check. If unspecified, all files will be checked.", nargs="*"
)
parser.add_argument("--rootdir", default=os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")),
                    help="Root directory to examine.")
parser.add_argument("--boilerplate-dir", 
                    default=os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")), 
                    "hack/boilerplate"),
                    help="Directory containing boilerplate files.")
parser.add_argument(
    "-v", "--verbose", help="Provide verbose output for files that do not pass.", action="store_true"
)
args = parser.parse_args()

# Set up verbose output
verbose_out = sys.stderr if args.verbose else None

def get_boilerplate_refs():
    """Retrieve boilerplate references from the specified directory."""
    refs = {}
    for path in glob.glob(os.path.join(args.boilerplate_dir, "boilerplate.*.txt")):
        extension = os.path.basename(path).split(".")[1]
        with open(path, "r") as ref_file:
            refs[extension] = ref_file.read().splitlines()
    return refs

def is_generated_file(data, regexs):
    """Determine if the file is an auto-generated file based on regex patterns."""
    return regexs["generated"].search(data)

def get_file_extension(filename):
    """Retrieve the file extension of the given filename."""
    return os.path.splitext(filename)[1].split(".")[-1].lower()

def file_passes_check(filename, refs, regexs):
    """Check if a file passes the boilerplate validation."""
    try:
        with open(filename) as stream:
            data = stream.read()
    except OSError as exc:
        print(f"Unable to open {filename}: {exc}", file=verbose_out)
        return False

    generated = is_generated_file(data, regexs)
    extension = get_file_extension(filename)
    if generated and extension == "go":
        extension = "generatego"

    ref = refs.get(extension, refs.get(os.path.basename(filename), []))

    # Remove extra content from the top of files based on extension
    if extension in ("go", "generatego"):
        data, _ = regexs["go_build_constraints"].subn("", data, 1)
    elif extension in ["sh", "py"]:
        data, _ = regexs["shebang"].subn("", data, 1)

    data = data.splitlines()

    # If file is smaller than the reference, it fails
    if len(ref) > len(data):
        print(f"File {filename} smaller than reference ({len(data)} < {len(ref)})", file=verbose_out)
        return False

    data = data[:len(ref)]

    for line in data:
        if regexs["year"].search(line):
            print(
                f"File {filename} has the YEAR field, but it should not be in generated file" if generated else
                f"File {filename} has the YEAR field, but is missing the year of date",
                file=verbose_out,
            )
            return False

    if not generated:
        data = [regexs["date"].sub("YEAR", line) for line in data]

    if ref != data:
        print(f"Header in {filename} does not match reference. Showing diff:", file=verbose_out)
        if args.verbose:
            for line in difflib.unified_diff(ref, data, "reference", filename, lineterm=""):
                print(line, file=verbose_out)
        return False

    return True

def normalize_files(files):
    """Normalize file paths and filter out unwanted directories."""
    filtered_files = []
    for pathname in files:
        if not any(skip in pathname for skip in skipped_names): # type: ignore
            full_path = os.path.join(args.rootdir, pathname) if not os.path.isabs(pathname) else pathname
            filtered_files.append(full_path)
    return filtered_files

def get_files_to_check(extensions):
    """Retrieve a list of files to check based on the specified extensions."""
    files = args.filenames if args.filenames else [
        os.path.join(root, name) for root, dirs, filenames in os.walk(args.rootdir)
        for name in filenames if get_file_extension(name) in extensions or name in extensions
    ]
    return normalize_files(files)

def get_current_year_regex():
    """Generate a regex pattern that matches any year from 2014 to the current year."""
    current_year = datetime.datetime.now().year
    return f"({'|'.join(str(year) for year in range(2014, current_year + 1))})"

def compile_regex_patterns():
    """Compile and return the necessary regex patterns."""
    return {
        "year": re.compile(r"YEAR"),
        "date": re.compile(get_current_year_regex()),
        "go_build_constraints": re.compile(r"^(//(go:build| \+build).*\n)+\n", re.MULTILINE),
        "shebang": re.compile(r"^(#!.*\n)\n*", re.MULTILINE),
        "generated": re.compile(r"^[/*#]+ +.* DO NOT EDIT\.$", re.MULTILINE),
    }

def main():
    regexs = compile_regex_patterns()
    refs = get_boilerplate_refs()
    files_to_check = get_files_to_check(refs.keys())

    for filename in files_to_check:
        if not file_passes_check(filename, refs, regexs):
            print(f"Failed: {filename}")

    return 0

if __name__ == "__main__":
    sys.exit(main())
