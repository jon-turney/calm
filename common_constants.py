#
# cygwin project constants
#

# XXX: make these settable via command line options, with defaults?

# base directory for maintainer upload directories
HOMEDIRS='/sourceware/cygwin-staging/home'

# the 'release area', contains all released files, which are rsync'ed to mirrors
#FTP='/var/ftp/pub/cygwin'
FTP='/var/ftp/pub/cygwin-test'

# logs are always emailed to these addresses
#EMAIL='jturney'
EMAILS='jon.turney@dronecode.org.uk'

# these maintainers can upload orphaned packages as well
ORPHANMAINT="Yaakov Selkowitz"

# architectures we support
ARCHES=['x86', 'x86_64' ]

# base directory for HTML output
HTMLBASE='/www/sourceware/htdocs/cygwin/packages'

# the list of packages with maintainers
PKGMAINT='/www/sourceware/htdocs/cygwin/cygwin-pkg-maint'
