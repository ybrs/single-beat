from setuptools import setup

with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
    name='single-beat',
    version='0.6.2',
    long_description=long_description,
    long_description_content_type="text/markdown",
    description='ensures only one instance of your process across your servers',
    url='https://github.com/ybrs/single-beat',
    license='MIT',
    packages=['singlebeat'],
    zip_safe=True,
    python_requires='>3.7.0',
    install_requires=[
        'redis >= 2.9.1',
        'aioredis >= 2.0',
        'Click>=7.0'
    ],
    test_require=[
        'psutil>=5.2.2'
    ],
    entry_points={
        'console_scripts': [
            'single-beat = singlebeat.beat:main',
            'single-beat-cli = singlebeat.cli:main',
        ],
    }
)
