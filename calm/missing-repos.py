import os

from . import common_constants
from . import maintainers


pl = maintainers.pkg_list(common_constants.PKGMAINT)

for p in pl.values():
    repo = '/git/cygwin-packages/%s.git' % p
    if not os.path.exists(repo):
        print('package %s, maintainer(s) %s' % (p, p.maintainers()))
