#!/usr/bin/env bash

if [[ $NERSC_HOST == "muller" ]]; then
    module swap PrgEnv-gnu
    module load boost

    if [ ! -d "elbencho" ]; then
        git clone git@github.com:breuner/elbencho.git
    fi

    cd elbencho

    git checkout 5033e197682a8de947fe8eb44db5d89eadf8e7b2

    if [ ! -d "bin" ]; then
        mkdir bin
    fi

    LDFLAGS_AIO=" " LIBAIO_SUPPORT=0 make -j

    if [ ! -d "bin.$NERSC_HOST" ]; then
        mkdir "bin.$NERSC_HOST"
    fi
    mv -v bin/* "bin.${NERSC_HOST}/"
fi
