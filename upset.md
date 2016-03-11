---
upset
=====
---

The upset script on sourceware does lots of stuff. This document
attempts to describe what it currently does, and enumerate it’s problems
and shortcomings.

A package
---------

A package consists of: a most one install tar file
(_package-version-release.tar.compression_), at most one source tar file
(_package-version-release-src.tar.compression_), a `setup.hint` file.

.xz, .bz2 and .gzip _compression_ are permitted. genini also allows
.lzma.

version and release **must** start with a digit. release **must not** contain a
hyphen.

Issue: Both _version_ and _release_ historically have been allowed to
contain a hyphen. The ambiguity in splitting _package-version_ can be
resolved in upset since the containing directory is always named
_package_, but elsewhere this is may not be possible. In some places (?)
the _version_ is assumed to start at the first digit after a hyphen. This
makes package names like qt-3-gcc3 invalid.

Issue: Since `setup.hint` is not _package-version-release_ named, all
packages in the same directory must share the same `setup.hint`. This
causes problems when the dependencies change between package versions.

Issue: If more than one install or source file exists for the same
_package-version-release_ (i.e. with different _compression_), it’s
undefined which one will be used, and is not reported as a problem.

A maintainer
------------

A maintainer has the ability to upload arbitrary files to their upload
area.

Each package has zero (if it is orphaned) or more maintainers.

upset accepts files for a set of packages from the upload area.

The base names of the packages are listed in `cygwin-pkg-maint`. A
package is considered to match if it is located in path which contains a
directory starting with the base package name (ignoring case), followed
by a word boundary.

Certain maintainers are granted the ability to upload all orphaned
packages as well.

Issue: The package name matching rule avoids the need to explicitly
specify foo, foo-doc, foo-debug, foo\_rebase, libfoo1,
girepository-foo, etc., but means that a maintainer can upload a package
with any name in the paths they are permitted to use. The only thing
preventing arbitrary package uploads is that the same package is not
allowed to exist at multiple paths.

Issue: Rather than parsing `cygwin-pkg-maint`, upset reads a `!packages` file left
in the maintainer upload directory by `mkpkgdir` for the list of packages
for a maintainer. Hopefully permissions prevent a maintainer from
overwriting `!packages`.

Issue: Maintainers are allowed to upload a replacement for an existing
tar file. This should not be permitted as (i) packages are supposed to
be immutable, and (ii) when someone has already installed the previous
tar file, setup (correctly) reports that it has the file in the download
cache, but `setup.ini` gives a different hash, and requires manual removal
of the previous tar file to proceed. To enforce this does open up the
possibility not being able to replace a corrupt upload, so perhaps some
additional checking should be done of the upload (e.g. check against an
uploaded sh512.sum) before the file is accepted.

`setup.hint` parsing
--------------------

Issue: The encoding of `setup.hint` is unspecified. Historically both
ISO-8859-1 and UTF-8 have been used. UTF-8 probably displays correctly
in the HTML package pages, but not in setup. Either specify UTF-8 and
eventually fix setup, or specify ASCII.

Issue: The `setup.hint` **sdesc** gets mangled before being put into `setup.ini`
(but not the HTML package list). In particular, it is forced to start
with a capital letter (which is incorrect when the **sdesc** starts with a
command name which is properly lower-case), and any text up to and
including the first colon is removed, presumably in an effort to prevent
people writing the package name again (which mangles perl and ruby
module names)

Issue: In `setup.ini` key values, a multi-line double-quoted value is
terminated only by a double-quote at the end of the line, and embedded
double-quotes are transformed to single-quotes. There is no escaping of
embedded double-quotes, and no way to represent one. In addition,
spaces after the leading quote are magically stripped.

Issue: **sdesc** is expected to be a single line, but this is not checked
for.

Issue: Erroneously transposed **sdesc** and **ldesc** seems to happen
occasionally, and is not detected.

Issue: The documentation claims that a **category** name could be multiple
words enclosed in quotation marks, but I don’t think this would be
handled correctly.

Issue: genini validates that **category** names are in a fixed list. upset
does not.

Issue: genini requires that **sdesc** and **ldesc** are double-quoted. upset
does not.

Issue: It’s unclear if or how source-only packages should be explicitly
identified as such. Some are marked with **skip**, which leads to them
being omitted from `setup.ini` and the HTML package list, whereas some
just have no install versions, which leads to them appearing in those
lists.

Paths
-----

Various paths are hardcoded into upset or the script used to invoke it.

-   The package search and file list web pages
    `/www/sourceware/htdocs/cygwin/packages/`
-   The release area `/var/ftp/pub/cygwin/arch/release/`
-   The maintainer upload directory `/sourceware/cygwin-staging/home/`
-   The deleted files vault `/sourceware/snapshot-tmp/cygwin`

What it does
------------

1.  Upset is run from cron at 10 minutes past the hour
2.  Extract the current setup version from the `setup-arch.exe` symlink’s
    target
3.  Make a list of all the HTML package list pages
4.  Read the existing `setup.ini`
5.  Recursively scan directories given on the command line (the release
    area and maintainer upload directory)

  - it’s an error if the same package name is used with different
    relative paths below the base directory, it’s an error if there is
    no `setup.hint` file
  - files with a timestamp newer than `!ready` aren’t processed
  - parse `setup.hint` file
  - record tar files
  - for each package
    - unless package is marked **skip**
    - assign versions to stability levels

6.  Delete any `!ready` files
7.  Move files requested for deletion to vault, and build a list of
    files to move from upload to release area

  - stop if an error occurred

8.  Update the package listing pages

  - If it doesn’t already exist
    - Write a HTML file named after the tar file
      `package/package-version-release(-src)`, listing it’s contents, to be
      used by the website package search.
    - Also create a `.htaccess` file in `package/`
  - Remove listing files for which there is no corresponding tar file
  - Remove any empty listing directories
  - Write `packages.inc`, a HTML list of packages used by the website
    package list page.

9.  As a side effect of the previous step, if we are reading the file
    list for the package, each filename is checked for **autodep**.
    Otherwise, any **autodep** **requires** from the existing `setup.ini` are
    preserved. For details, see below.
10. Write temporary file containing new `setup.ini` contents

  - header
    - a comment indicating the file is automatically generated
    - **release**, a release identifier, as given on command line (‘cygwin’)
    - **arch**, as given on command line
    - **setup-timestamp**, the current time
    - **setup-version**, as determined above
  - for each package
    - do nothing if **skip** or no install tar files (i.e. is source only)
    - must have **category** and **sdesc**
    - **ldesc**, **requires** and **message** lines are suppressed if empty
    - packages listed in **requires** must exist, and have a **curr** version
    - **category** names are forced to start with a capital letter
    - if there is no source tar file, follow **external-source**
    - write package entry
  - stop if an error occurred

11. Move files in the list of file to move

  - stop if an error occurred

12. If more than the **setup-timestamp** has changed, replace `setup.ini` with
    the temporary file, and bz2 compress it, otherwise discard the
    temporary file
13. Send email of errors and warnings to all maintainers
14. gpg sign `setup.ini`, `setup.bz2`

Issue: Step 1 means maintainers have to wait up to an hour to discover
if their were any problems with their upload. Perhaps it would be
better if upset ran on-demand.

Issue: Step 2 seems very fragile. There is fallback code to extract
the version from the setup binary, but this won’t work on UPX compressed
binaries. UPX does have a the ability to leave some resources
uncompressed, for use with the manifest, maybe something could be done
using that.

Issue: The only data which appears to be retained from step 4 is **autodep**
dependencies, as described later.

Issue: To reuse the step 5 mechanism for the release area, a file
`!always_ready` is treated as a `!ready` file with a mtime of MAXINT, and
such a file must exist in the release area.

Issue: Step 8 has the problem that if a package’s **sdesc** is updated, this
page does not change to reflect it. (Although re-writing these pages on
every run would have a prohibitive performance cost, since reading the
file catalogue from a tar file is expensive)

Issue: In step 8, cleaning up empty listing directories isn’t working
because there is always a `.htaccess` present which causes rmdir to fail

Issue: Step 8 presents the file timestamps as reported by tar. They
are, I think in UTC, but perhaps we could stand to be clearer about
that, and ensure that is the case if the script is run in a non-UTC
timezone?

Issue: The upshot of step 9 is that the HTML package file listing acts
as a marker that the package file list has been read on a previous run,
and the **requires** for the package read from `setup.ini` in step 4 contain
**autodep**s which should be preserved

Issue: In step 13, all maintainers are sent the same mail. It would be
more logical to send a maintainer errors for only their packages, and
send project leads all errors.

Issue: In step 14, gpg signatures are always regenerated, even if
`setup.ini` didn’t change, which causes some unnecessary mirror traffic.

Issue: No verbose mode. If you want to investigate a problem you have
to add debug output to diagnose what happened.

Issue: The environment that upset is supposed to run in is undocumented.
This makes duplicating it to test changes a challenge.

Issue: There are numerous other package set integrity checks which could
be done.

Issue: upset tries to operate in an atomic fashion, only changing the
package set if the result is valid, but fails in several areas. e.g.
nothing prevents deleting a file which is required by another package.

### Sorting

For `setup.ini` and `package.inc`, package names are sorted in an order
which puts numbers first, then letters (case-insensitively), then
punctuation.

autodep, noautodep, incver\_ifdep
---------------------------------

If we are reading the file list for the package, each non-symlink
pathname is matched against the **autodep** regexes for all packages. If a
regex matches, the package with the **autodep** is added to the **requires** for
that package, unless it is listed in **noautodep**.

**incver\_ifdep** causes the package and source package to be renamed with
an incremented version number. The unimplemented **verpat** gives the
format of _package-version-release_ for the package. At the moment
_version_ is assumed to be a sequence of only digits, at least 3 digits
long.

Otherwise, any **autodep** **requires** from the existing `setup.ini` are
preserved.

Empty archives
--------------

A compressed empty file may appear in place of a compressed empty tar
archive. A file of 32 bytes or less is assumed to be one of these
compressed empty files. The reasons for this are lost in the mists of
history...
