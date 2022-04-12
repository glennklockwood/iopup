#!/usr/bin/env bash

if [[ $NERSC_HOST == "muller" ]]; then
    module swap PrgEnv-gnu

    if [ ! -d "ior" ]; then
        # git clone git@github.com:hpc/ior.git
        git clone git@github.com:glennklockwood/ior.git
    fi

    cd ior

    # git checkout 0410a38e985e0862a9fd9abec017abffc4c5fc43
    git checkout feature/incompress

    if [ ! -f "configure" ]; then
        ./bootstrap
    fi

    if [ ! -d "build.$NERSC_HOST" ]; then
        mkdir build.$NERSC_HOST
    fi
    cd build.$NERSC_HOST

    if [ ! -f "Makefile" ]; then
        ../configure
    fi

    make

    INSTALL_DIR="../bin.$NERSC_HOST"

    if [ ! -d "$INSTALL_DIR" ]; then
        mkdir "$INSTALL_DIR"
    fi
    mv -v src/ior src/mdtest src/md-workbench "${INSTALL_DIR}/"
fi
