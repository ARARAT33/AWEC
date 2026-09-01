from setuptools import setup, find_packages

setup(
    name="awec",
    version="3.0.0",
    description="Production-grade, resumable, archive-grade universal web acquisition engine",
    author="AWEC Team",
    packages=find_packages(),
    py_modules=["awescan"],
    install_requires=[
        "aiohttp>=3.9.0",
        "beautifulsoup4>=4.12.0",
        "lxml>=5.0.0",
        "PySide6>=6.7.0",
        "boto3>=1.35.0",
        "python-docx>=1.1.0",
        "brotli>=1.1.0",
        "internetarchive>=5.0.0",
        "warcio>=1.8.0",
        "pyyaml>=6.0",
    ],
    entry_points={
        "console_scripts": [
            "awescan=awescan:main",
        ],
    },
    python_requires=">=3.10",
)
