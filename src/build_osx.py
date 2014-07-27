# coding=utf-8
from setuptools import setup

name = "Bitmessage"
version = "0.4.2"
main_script = ["bitmessagemain.py"]

setup(
    name=name,
    version=version,
    app=main_script,
    setup_requires=["py2app"],
    options=dict(
        py2app=dict(
            resources=["images", "translations"],
            includes=['sip', 'PyQt4._qt'],
            iconfile="images/bitmessage.icns"
        )
    )
)
