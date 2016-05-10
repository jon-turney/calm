from setuptools import setup

setup(
    name='calm',
    version='20160511',
    description='Cygwin packaging maintenance tool',
    long_description=open('README.md').read(),
    author='Jon Turney',
    author_email='jon.turney@dronecode.org.uk',
    license='MIT',
    packages=['calm'],
    install_requires=['dirq'],
    entry_points= {
        'console_scripts': [
            'calm = calm.calm:main',
            'mksetupini = calm.mksetupini:main',
        ],
    },
    url='https://cygwin.com/git/?p=cygwin-apps/calm.git',
    test_suite='tests',
)
