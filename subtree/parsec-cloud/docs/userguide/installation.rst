.. _doc_userguide_install_client:


Install Parsec client
=====================

Windows
-------

Windows installer is available at the latest stable version on `parsec.cloud <https://parsec.cloud/get-parsec>`_. Otherwise, it is possible to download a specific Parsec version on `GitHub <https://github.com/Scille/parsec/releases/latest>`_, for exemple to make Parsec work on a 32 bits computer (installers named ``parsec-vX.Y.Z-win32-setup.exe``).


MacOS
-----

Parsec is not yet available on MacOS Big Sur (>= 11.0).

MacOS (<= 10.15) installer is available as a DMG installer on `GitHub <https://github.com/Scille/parsec/releases/latest>`_ (installer named ``parsec-vX.Y.Z-macos-amd64.dmg``).


Linux
-----

Parsec is available on Snap:

.. raw:: html

    <iframe src="https://snapcraft.io/parsec/embedded?button=black" frameborder="0" width="100%" height="350px" style="border: 1px solid #CCC; border-radius: 2px;"></iframe>

If you are familiar with Snap, you may notice that Parsec snap is provided in classic mode (i.e. without sandbox). This is needed because Parsec needs `Fuse <https://en.wikipedia.org/wiki/Filesystem_in_Userspace>`_ to mount your data as a virtual directory, which is not allowed by the Snap sandbox.


.. note::

    You can install the snap from the command line by doing:

    .. code-block:: shell

        sudo snap install parsec --classic


Via pip
-------

Given that Parsec is written in Python, an alternative is to install it through `pip (the Python package repository) <https://pypi.org/project/parsec-cloud/>`_.

.. code-block:: shell

    pip install parsec-cloud

Or intall it with all its dependencies, for the GUI.

.. code-block:: shell

    pip install parsec-cloud[all]

.. note::

    Parsec requires Python >= 3.6 to work.
