import random
import cocotb
from cocotb.utils import get_sim_time
from cocotb.clock import Clock
from cocotb.triggers import Timer,RisingEdge
from functools import wraps

import logging

import dut_utils
from models import AxiEthernetDutWithMirror,AxiEthernetWrapper

##################
# Configure PRNG #
##################

# Seed for the PRNG
# Reseeded before each test so tests are repeatable without rerunning the whole test suite (assuming perfeclty restored state between tests)
GLOBAL_SEED = 1784024865#random.randint(0,2**32-1)
logging.info(f"GLOBAL_SEED={GLOBAL_SEED}") # TODO change logger
random.seed(GLOBAL_SEED)

#############################
# Define test configuration #
#############################
class TestConfiguration:
    # Randomise the order tests run in
    randomise_test_order = False

    # DUT will not be reset between tests
    # Each test should be responsible for re-initialising the DUT
    between_tests = "RESET"
    # "RESET":              Reset the DUT between tests with the reset signal
    # "REINITIALISE":       Do not reset the DUT between tests, but pop any packets and let TX drain.

    # Run a health test after EVERY test
    # Normally health tests are only run after tests that explicitly specify it
    # e.g. because they are testing for leaving the DUT in a deadlocked state
    # Adds about 0.06 seconds to each test on my machine
    health_test_all = False

    # Only run tests that have been tagged with one of the tags in this list
    tag_matcher = lambda x:True
    # Create a callable that takes a list of tags on a test and returns True if the test should be run, False otherwise

async def custom_clock(clk, period, phase_offset=0, unit="ns"):
    # pre-construct triggers for performance
    high_time = Timer(period/2, unit=unit)
    low_time = Timer(period/2, unit=unit)
    if phase_offset:
        await Timer(phase_offset, unit=unit)
    while True:
        clk.value = 1
        await high_time
        clk.value = 0
        await low_time

##########################
# Create test decorators #
##########################
def create_test(
    tags = [],                              # tags applied to the test
    with_mirror = True,                     # create a software mirror for the DUT and assert all 'get' calls match
    health_test_after = False,              # run a health test after this test
    promiscuous = False,                    # initial configuration for the DUT
    loopback = False,                       # initial configuration for the DUT
    mac_addr = None,                        # initial configuration for the DUT
    prep_tx_buffer = False,                 # write random data to the TX buffer first
    order = 0,                              # relative ordering for this test. Overridden by the test runner if randomise_test_order is True
):
    def decorator(func):
        if not TestConfiguration.tag_matcher(tags):
            return func
        else:
            # Define the test
            @cocotb.test() # TODO randomise order
            @wraps(func)
            async def wrapped_function(dut):
                # Seed the PRNG for this test
                random.seed(GLOBAL_SEED) # TODO this means any pre-test randomisation will be identical for all tests, not ideal. Consider adding a hash of the test name or something

                # Start the clocks
                cocotb.start_soon(custom_clock(
                    dut.clk_125M_i, 8, phase_offset=0, unit="ns"
                ))
                cocotb.start_soon(custom_clock(
                    dut.clk_125M_quad_i, 8, phase_offset=2, unit="ns"
                ))
                cocotb.start_soon(custom_clock(
                    dut.clk_200M_i, 5, phase_offset=0, unit="ns"
                ))

                # Wrap the DUT
                # Add the mirror if requested
                if with_mirror:
                    dut_wrapped = AxiEthernetDutWithMirror(dut)
                else:
                    dut_wrapped = AxiEthernetWrapper(dut)

                # Reset or reinitialise the DUT
                if TestConfiguration.between_tests == "RESET":
                    await dut_wrapped.reset()
                elif TestConfiguration.between_tests == "REINITIALISE":
                    await dut_utils.reinitialise_dut_state(dut_wrapped)

                # Configure the DUT
                if promiscuous or loopback:
                    await dut_wrapped.mode_set(promiscuous,loopback)
                if mac_addr is not None:
                    await dut_wrapped.mac_address_set(mac_addr)
                if prep_tx_buffer: # TODO allowing writing number of words
                    await dut_utils.prep_tx_buffer(dut_wrapped)

                # Run the test
                try:
                    await func(dut_wrapped)
                    # Run a health test if requested
                    if health_test_after or TestConfiguration.health_test_all:
                        await dut_utils.health_test(dut_wrapped if not with_mirror else dut_wrapped.wrapper)
                    await Timer(100, 'ns')

                    dut_wrapped.dut.tests_passed.value = int(dut_wrapped.dut.tests_passed.value) + 1
                except Exception as e:
                    dut_wrapped.dut.tests_failed.value = int(dut_wrapped.dut.tests_failed.value) + 1
                    raise e
                finally:
                    dut_wrapped.dut.tests_done.value = int(dut_wrapped.dut.tests_done.value) + 1
            return wrapped_function
    return decorator

# Wow what a piece of code that is
# Not just a nested function but a *conditionally-defined doubly-nested function*
# It's got coroutines, decorators, callbacks
# At this point Python is just showing off!
