#!/usr/bin/env bash

mkdir -p reports
pushd build/lowrisc_mocha_axi_ethernet_0/sim
verilator_coverage --annotate-min 1 --annotate . coverage.dat
verilator_coverage --annotate-min 1 --report summary,hier coverage.dat > ../../../reports/coverage_report.txt
grep -ir %00 . > ../../../reports/coverage_gaps.txt
popd

echo
echo "See coverage report in reports/coverage_report.txt"
echo "See coverage gaps in reports/coverage_gaps.txt"
echo "See annotated coverage in build/lowrisc_mocha_axi_ethernet_0/sim/*.sv"
