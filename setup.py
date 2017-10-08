from setuptools import setup

setup(
    name='calm',
    version='20171008',
    description='Cygwin packaging maintenance tool',
    long_description=open('README.md').read(),
    author='Jon Turney',
    author_email='jon.turney@dronecode.org.uk',
    license='MIT',
    packages=['calm'],
    entry_points= {
        'console_scripts': [
            'calm = calm.calm:main',
            'mksetupini = calm.mksetupini:main',
            'calm-mkgitoliteconf = calm.mkgitoliteconf:main',
            'dedup-source = calm.dedupsrc:main',
        ],
    },
    url='https://cygwin.com/git/?p=cygwin-apps/calm.git',
    test_suite='tests',
)
