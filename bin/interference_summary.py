#!/usr/bin/env python3

import os
import glob
import itertools
import argparse
import warnings

import numpy
import pandas

from n10ioana.load import load_contention_dataset
from n10ioana.contention import validate_contention_dataset, IncompleteDatasetError, JobOverlapError

def load_contention_datasets(*filenames):
    input_files = []
    for filename in filenames:
        if os.path.isdir(filename):
            input_files.append(glob.glob(os.path.join(filename, "primary_*.out")))
            input_files.append(glob.glob(os.path.join(filename, "secondary_*.out")))
        else:
            input_files.append(glob.glob(filename))

    results = None
    for filename in itertools.chain(*input_files):
        try:
            result = load_contention_dataset(filename)
        except ValueError:
            continue
        if results is None:
            results = result
        else:
            results = pandas.concat((results, result), axis=0, sort=True)

    return results

def performance_frame(results):
    performance = results.pivot_table(
        index=["primary_nodes", "secondary_nodes"],
        columns=["contention", "workload_id"],
        values=["performance"],
        aggfunc=numpy.mean)

    # drop the "performance" column
    performance.columns = performance.columns.droplevel(0)
    return performance

def loss_frame(performance):
    losses = []
    for (n_primary, n_secondary), row in performance.iterrows():
        loss = {}
        for workload_id in "primary", "secondary":
            try:
                loss[workload_id] = row.loc[("quiet", workload_id)] - row.loc[("noisy", workload_id)]
                loss[workload_id] *= 100.0 / row.loc[("quiet", workload_id)]
            except KeyError:
                pass
        if loss:
            losses.append(loss)

    loss = pandas.DataFrame.from_records(losses, index=performance.index)
    loss.columns.name = "loss"

    return loss

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("file", nargs="*", type=str, default=os.getcwd(), help="Directory to scan for intereference outputs")
    args = parser.parse_args()

    results = load_contention_datasets(*(args.file))

    try:
        validate_contention_dataset(results)
    except (IncompleteDatasetError, JobOverlapError) as err:
        warnings.warn(str(err))

    if results is None:
        raise FileNotFoundError("No valid inputs found")

    performance_df = performance_frame(results)

    loss_df = loss_frame(performance_df)

    with pandas.option_context('display.max_rows', None, 'display.max_columns', None):
        print("-----" * 16)
        print("Performance\n" + "-----" * 16)
        # print "quiet" before "noisy"
        print(performance_df[sorted(performance_df.columns, reverse=True)])
        print("-----" * 16)
        print("Performance Loss (%)\n" + "-----" * 16)
        print(loss_df)
