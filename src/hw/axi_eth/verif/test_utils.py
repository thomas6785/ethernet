import random
import cocotb
from cocotb.utils import get_sim_time
from cocotb.clock import Clock
from cocotb.triggers import Timer,with_timeout
from functools import wraps

import logging

import dut_utils
from models import AxiEthernetDutWithMirror,AxiEthernetWrapper

##################
# Configure PRNG #
##################

# Seed for the PRNG
# Reseeded before each test so tests are repeatable without rerunning the whole test suite (assuming perfeclty restored state between tests)
GLOBAL_SEED = random.randint(0,2**32-1)
print(f"GLOBAL_SEED={GLOBAL_SEED}") # TODO change logger
random.seed(GLOBAL_SEED)

##################
# Tags for tests #
##################

class Tags():
    # All tests should be given one of these tags:
    SOLO  = 0    # for running a single test in isolation, useful for development
    MICRO = 10   # micro-test suite, really only useful for testing the testbench configuration, only cover one TX, one RX, and one loopback
    SMOKE = 20   # tests with the 'smoke' tag should cover basic 'hot paths' of the DUT and run quickly
    MAIN  = 30   # this tag will include MOST tests but exclude obscure edge cases, avoid duplicate tests, and avoid long-running tests
    EDGE  = 40   # this tag covers everything else
    # they tags should be used mutually exclusively
    # when running one level, all lower levels should run too

    # for now that is all, but more tags can be added as needed e.g. to differentiate tests by the features they hit
    # but the test suite isn't really large enough to justify the effort in maintaining a complex tagging system

#############################
# Define test configuration #
#############################
class TestConfiguration:
    # Randomise the order tests run in
    randomise_test_order = True

    # Each test should be responsible for re-initialising the DUT
    # We may choose to reset using the reset pin, or re-initialise by draining the TX and RX buffers and overwriting all registers
    # Re-initialising is slower than resetting, but it is more realistic and may catch more bugs
    # Reinitialising makes reproducibility a bit more difficult - you can still re-run the whole suite but re-running a single test will not be perfectly reproducible
    between_tests = "REINITIALISE"
    # "RESET":              Reset the DUT between tests with the reset signal
    # "REINITIALISE":       Do not reset the DUT between tests, but pop any packets and let TX drain.

    # Run a health test after EVERY test
    # Normally health tests are only run after tests that explicitly specify it
    # e.g. because they are testing for leaving the DUT in a deadlocked state
    # Adds about 0.06 seconds to each test on my machine
    health_test_all = True

    # Only run tests that match this callable
    tag_matcher = lambda x:True
    #tag_matcher = lambda tags:Tags.SOLO in tags
    #tag_matcher = lambda tags:min(tags) <= Tags.MAIN

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
    skip = False                            # skip this test
):
    is_micro = Tags.MICRO in tags
    is_smoke = Tags.SMOKE in tags
    is_main  = Tags.MAIN  in tags
    is_edge  = Tags.EDGE  in tags
    if sum([is_micro,is_smoke,is_main,is_edge]) != 1:
        raise ValueError(f"Test has tags: {tags}. Tests should have exaclty one of the mutually-exclusive tags: MICRO, SMOKE, MAIN, EDGE")

    def decorator(func):
        if not TestConfiguration.tag_matcher(tags):
            return func
        else:
            # Define the test
            @cocotb.test(
                stage=order if not TestConfiguration.randomise_test_order else random.randint(0,1000),
                skip=skip
            )
            @wraps(func)
            async def wrapped_function(dut):
                # Seed the PRNG for this test
                random.seed(GLOBAL_SEED+hash(func.__name__))
                # add a hash of the test name to the random seed
                # this is because a lot of tests share common startup code, so if we use the same seed that code will always generate the same data

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
                if TestConfiguration.between_tests == "RESET" or dut_wrapped.dut.tests_done.value == 0: # always reset before the first test
                    await dut_wrapped.reset()
                elif TestConfiguration.between_tests == "REINITIALISE":
                    await dut_utils.reinitialise_dut_state(dut_wrapped if not with_mirror else dut_wrapped.wrapper)

                # Configure the DUT
                if promiscuous or loopback:
                    await dut_wrapped.mode_set(promiscuous,loopback)
                if mac_addr is not None:
                    await dut_wrapped.mac_address_set(mac_addr)
                if prep_tx_buffer: # TODO allowing writing number of words
                    await dut_utils.prep_tx_buffer(dut_wrapped)

                # Run the test
                # TODO this function needs a bit of cleaning up
                try:
                    await with_timeout(func(dut_wrapped),2000,"us")
                    # Run a health test if requested
                    if health_test_after or TestConfiguration.health_test_all:
                        await with_timeout(dut_utils.health_test(dut_wrapped if not with_mirror else dut_wrapped.wrapper),10,"us")
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

def randint(min,max):
    # Return a random integer between min and max, inclusive
    # but with a bias toward edge cases
    # using randomness for this is not ideal, it would be better to have parametrised tests that explicitly hit all edge cases
    # but cocotb makes parametrising tests a bit nasty so this will work for now as long as you run a lot of tests
    # and inspect the coverage metrics to ensure that all edge cases are being hit
    # Has a 15% probability of returning the min
    # 5% probability of min+1
    # 5% probability of max-1
    # 15% probability of max
    # 60% probability of a uniform random integer between min+2 and max-2
    if max-min < 8:
        return random.randint(min,max)
    r = random.random()
    if r < 0.15:
        return min
    elif r < 0.20:
        return min+1
    elif r < 0.80:
        return random.randint(min+2,max-2)
    elif r < 0.85:
        return max-1
    else:
        return max
