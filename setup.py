from setuptools import setup

setup(
    name='calm',
    use_scm_version=True,
    setup_requires=['setuptools_scm'],
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
