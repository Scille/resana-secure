from distutils.core import Extension, setup


def main():
    setup(
        name="tgbverifier",
        version="1.0.0",
        description="Checks that the DLL provided by TheGreenBow is correctly signed",
        author="SCILLE SAS",
        ext_modules=[
            Extension(
                "tgbverifier",
                sources=["src/tgbverifiermodule.c"],
                libraries=["wintrust", "crypt32"],
            )
        ],
    )


if __name__ == "__main__":
    main()
