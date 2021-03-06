# Utilities for TARDIS

from astropy import units as u, constants
from pyne import nucname
import numexpr as ne
import numpy as np
import pandas as pd
import os
import yaml
import re
import tardis
import logging

from collections import OrderedDict


k_B_cgs = constants.k_B.cgs.value
c_cgs = constants.c.cgs.value
h_cgs = constants.h.cgs.value
m_e_cgs = constants.m_e.cgs.value
e_charge_gauss = constants.e.gauss.value

class MalformedError(Exception):
    pass

class MalformedSpeciesError(MalformedError):

    def __init__(self, malformed_element_symbol):
        self.malformed_element_symbol = malformed_element_symbol

    def __str__(self):
        return 'Expecting a species notation (e.g. "Si 2", "Si II", "Fe IV") - supplied %s' % self.malformed_element_symbol


class MalformedElementSymbolError(MalformedError):

    def __init__(self, malformed_element_symbol):
        self.malformed_element_symbol = malformed_element_symbol

    def __str__(self):
        return 'Expecting an atomic symbol (e.g. Fe) - supplied %s' % self.malformed_element_symbol


class MalformedQuantityError(MalformedError):

    def __init__(self, malformed_quantity_string):
        self.malformed_quantity_string = malformed_quantity_string

    def __str__(self):
        return 'Expecting a quantity string(e.g. "5 km/s") for keyword - supplied %s' % self.malformed_quantity_string


logger = logging.getLogger(__name__)

tardis_dir = os.path.realpath(tardis.__path__[0])


def get_data_path(fname):
    return os.path.join(tardis_dir, 'data', fname)


def get_tests_data_path(fname):
    return os.path.join(tardis_dir, 'tests', 'data', fname)


atomic_symbols_data = np.recfromtxt(get_data_path('atomic_symbols.dat'),
                                    names=['atomic_number', 'symbol'])
symbol2atomic_number = OrderedDict(zip(atomic_symbols_data['symbol'],
                                       atomic_symbols_data['atomic_number']))
atomic_number2symbol = OrderedDict(atomic_symbols_data)


synpp_default_yaml_fname = get_data_path('synpp_default.yaml')


def int_to_roman(int_input):
    """
    from http://code.activestate.com/recipes/81611-roman-numerals/
    Convert an integer to Roman numerals.

    :param int_input: an integer between 1 and 3999
    :returns result: roman equivalent string of passed :param{int_input}

    Examples:
    >>> int_to_roman(0)
    Traceback (most recent call last):
    ValueError: Argument must be between 1 and 3999

    >>> int_to_roman(-1)
    Traceback (most recent call last):
    ValueError: Argument must be between 1 and 3999

    >>> int_to_roman(1.5)
    Traceback (most recent call last):
    TypeError: expected integer, got <type 'float'>

    >>> for i in range(1, 21): print int_to_roman(i),
    ...
    I II III IV V VI VII VIII IX X XI XII XIII XIV XV XVI XVII XVIII XIX XX
    >>> print int_to_roman(2000)
    MM
    >>> print int_to_roman(1999)
    MCMXCIX
    """
    if not isinstance(int_input, int):
        raise TypeError("Expected integer, got %s" % type(int_input))
    if not 0 < int_input < 4000:
        raise ValueError("Argument must be between 1 and 3999")

    int_roman_tuples = [(1000, 'M'), (900, 'CM'), (500, 'D'), (400, 'CD'),
                        (100 , 'C'), (90 , 'XC'), (50 , 'L'), (40 , 'XL'),
                        (10  , 'X'), (9  , 'IX'), (5  , 'V'), (4  , 'IV'), (1, 'I')]

    result = ''
    for (integer, roman) in int_roman_tuples:
        count = int(int_input / integer)
        result += roman * count
        int_input -= integer * count
    return result


def roman_to_int(roman_input):
    """
    from http://code.activestate.com/recipes/81611-roman-numerals/
    Convert a roman numeral to an integer.

    :param roman_input: a valid roman numeral string
    :returns sum: equivalent integer of passed :param{roman_input}

    >>> r = range(1, 4000)
    >>> nums = [int_to_roman(i) for i in r]
    >>> ints = [roman_to_int(n) for n in nums]
    >>> print r == ints
    1

    >>> roman_to_int('VVVIV')
    Traceback (most recent call last):
     ...
    ValueError: input is not a valid roman numeral: VVVIV
    >>> roman_to_int(1)
    Traceback (most recent call last):
     ...
    TypeError: expected string, got <type 'int'>
    >>> roman_to_int('a')
    Traceback (most recent call last):
     ...
    ValueError: input is not a valid roman numeral: A
    >>> roman_to_int('IL')
    Traceback (most recent call last):
     ...
    ValueError: input is not a valid roman numeral: IL
    """
    if not isinstance(roman_input, str):
        raise TypeError("expected string, got %s" % type(roman_input))

    roman_input = roman_input.upper()
    nums = ['M', 'D', 'C', 'L', 'X', 'V', 'I']
    ints = [1000, 500, 100, 50,  10,  5,   1]
    places = []
    for c in roman_input:
        if not c in nums:
            raise ValueError("input is not a valid roman numeral: %s" % roman_input)
    for i in range(len(roman_input)):
        c = roman_input[i]
        value = ints[nums.index(c)]
        # If the next place holds a larger number, this value is negative.
        try:
            nextvalue = ints[nums.index(roman_input[i +1])]
            if nextvalue > value:
                value *= -1
        except IndexError:
            # there is no next place.
            pass
        places.append(value)
    result = 0
    for n in places:
        result += n
    # Easiest test for validity...
    if int_to_roman(result) == roman_input:
        return result
    else:
        raise ValueError('input is not a valid roman numeral: %s' % roman_input)


def calculate_luminosity(spec_fname, distance, wavelength_column=0, wavelength_unit=u.angstrom, flux_column=1,
                         flux_unit=u.Unit('erg / (Angstrom cm2 s)')):

    #BAD STYLE change to parse quantity
    distance = u.Unit(distance)

    wavelength, flux = np.loadtxt(spec_fname, usecols=(wavelength_column, flux_column), unpack=True)

    flux_density = np.trapz(flux, wavelength) * (flux_unit * wavelength_unit)
    luminosity = (flux_density * 4 * np.pi * distance**2).to('erg/s')

    return luminosity.value, wavelength.min(), wavelength.max()

def create_synpp_yaml(radial1d_mdl, fname, shell_no=0, lines_db=None):
    logger.warning('Currently only works with Si and a special setup')
    if radial1d_mdl.atom_data.synpp_refs is not None:
        raise ValueError(
            'The current atom dataset does not contain the necesarry reference files (please contact the authors)')

    radial1d_mdl.atom_data.synpp_refs['ref_log_tau'] = -99.0
    for key, value in radial1d_mdl.atom_data.synpp_refs.iterrows():
        try:
            radial1d_mdl.atom_data.synpp_refs['ref_log_tau'].ix[key] = np.log10(
                radial1d_mdl.plasma.tau_sobolevs[0].ix[value['line_id']])
        except KeyError:
            pass


    relevant_synpp_refs = radial1d_mdl.atom_data.synpp_refs[radial1d_mdl.atom_data.synpp_refs['ref_log_tau'] > -50]

    with open(synpp_default_yaml_fname) as stream:
        yaml_reference = yaml.load(stream)

    if lines_db is not None:
        yaml_reference['opacity']['line_dir'] = os.path.join(lines_db, 'lines')
        yaml_reference['opacity']['line_dir'] = os.path.join(lines_db, 'refs.dat')

    yaml_reference['output']['min_wl'] = float(radial1d_mdl.runner.spectrum.wavelength.to('angstrom').value.min())
    yaml_reference['output']['max_wl'] = float(radial1d_mdl.runner.spectrum.wavelength.to('angstrom').value.max())


    #raise Exception("there's a problem here with units what units does synpp expect?")
    yaml_reference['opacity']['v_ref'] = float((radial1d_mdl.tardis_config.structure.v_inner[0].to('km/s') /
                                               (1000. * u.km / u.s)).value)
    yaml_reference['grid']['v_outer_max'] = float((radial1d_mdl.tardis_config.structure.v_outer[-1].to('km/s') /
                                                  (1000. * u.km / u.s)).value)

    #pdb.set_trace()

    yaml_setup = yaml_reference['setups'][0]
    yaml_setup['ions'] = []
    yaml_setup['log_tau'] = []
    yaml_setup['active'] = []
    yaml_setup['temp'] = []
    yaml_setup['v_min'] = []
    yaml_setup['v_max'] = []
    yaml_setup['aux'] = []

    for species, synpp_ref in relevant_synpp_refs.iterrows():
        yaml_setup['ions'].append(100 * species[0] + species[1])
        yaml_setup['log_tau'].append(float(synpp_ref['ref_log_tau']))
        yaml_setup['active'].append(True)
        yaml_setup['temp'].append(yaml_setup['t_phot'])
        yaml_setup['v_min'].append(yaml_reference['opacity']['v_ref'])
        yaml_setup['v_max'].append(yaml_reference['grid']['v_outer_max'])
        yaml_setup['aux'].append(1e200)
    with open(fname, 'w') as f:
        yaml.dump(yaml_reference, stream=f, explicit_start=True)


def intensity_black_body(nu, T):
    """
        Calculate the intensity of a black-body according to the following formula

        .. math::
            I(\\nu, T) = \\frac{2h\\nu^3}{c^2}\frac{1}{e^{h\\nu \\beta_\\textrm{rad}} - 1}

    """
    beta_rad = 1 / (k_B_cgs * T)
    coefficient = 2 * h_cgs / c_cgs ** 2
    intensity = ne.evaluate('coefficient * nu**3 / '
                            '(exp(h_cgs * nu * beta_rad) -1 )')
    return intensity

def savitzky_golay(y, window_size, order, deriv=0, rate=1):
    r"""Smooth (and optionally differentiate) data with a Savitzky-Golay filter.
    The Savitzky-Golay filter removes high frequency noise from data.
    It has the advantage of preserving the original shape and
    features of the signal better than other types of filtering
    approaches, such as moving averages techniques.
    Parameters
    ----------
    y : array_like, shape (N,)
        the values of the time history of the signal.
    window_size : int
        the length of the window. Must be an odd integer number.
    order : int
        the order of the polynomial used in the filtering.
        Must be less then `window_size` - 1.
    deriv: int
        the order of the derivative to compute (default = 0 means only smoothing)
    Returns
    -------
    ys : ndarray, shape (N)
        the smoothed signal (or it's n-th derivative).
    Notes
    -----
    The Savitzky-Golay is a type of low-pass filter, particularly
    suited for smoothing noisy data. The main idea behind this
    approach is to make for each point a least-square fit with a
    polynomial of high order over a odd-sized window centered at
    the point.
    Examples
    --------
    t = np.linspace(-4, 4, 500)
    y = np.exp( -t**2 ) + np.random.normal(0, 0.05, t.shape)
    ysg = savitzky_golay(y, window_size=31, order=4)
    import matplotlib.pyplot as plt
    plt.plot(t, y, label='Noisy signal')
    plt.plot(t, np.exp(-t**2), 'k', lw=1.5, label='Original signal')
    plt.plot(t, ysg, 'r', label='Filtered signal')
    plt.legend()
    plt.show()
    References
    ----------
    .. [1] A. Savitzky, M. J. E. Golay, Smoothing and Differentiation of
       Data by Simplified Least Squares Procedures. Analytical
       Chemistry, 1964, 36 (8), pp 1627-1639.
    .. [2] Numerical Recipes 3rd Edition: The Art of Scientific Computing
       W.H. Press, S.A. Teukolsky, W.T. Vetterling, B.P. Flannery
       Cambridge University Press ISBN-13: 9780521880688
    """
    import numpy as np
    from math import factorial

    try:
        window_size = np.abs(np.int(window_size))
        order = np.abs(np.int(order))
    except ValueError, msg:
        raise ValueError("window_size and order have to be of type int")
    if window_size % 2 != 1 or window_size < 1:
        raise TypeError("window_size size must be a positive odd number")
    if window_size < order + 2:
        raise TypeError("window_size is too small for the polynomials order")
    order_range = range(order+1)
    half_window = (window_size -1) // 2
    # precompute coefficients
    b = np.mat([[k**i for i in order_range] for k in range(-half_window, half_window+1)])
    m = np.linalg.pinv(b).A[deriv] * rate**deriv * factorial(deriv)
    # pad the signal at the extremes with
    # values taken from the signal itself
    firstvals = y[0] - np.abs( y[1:half_window+1][::-1] - y[0] )
    lastvals = y[-1] + np.abs(y[-half_window-1:-1][::-1] - y[-1])
    y = np.concatenate((firstvals, y, lastvals))
    return np.convolve( m[::-1], y, mode='valid')


def species_tuple_to_string(species_tuple, roman_numerals=True):
    atomic_number, ion_number = species_tuple
    element_symbol = atomic_number2symbol[atomic_number]
    if roman_numerals:
        roman_ion_number = int_to_roman(ion_number+1)
        return '%s %s' % (element_symbol, roman_ion_number)
    else:
        return '%s %d' % (element_symbol, ion_number)


def species_string_to_tuple(species_string):

    try:
        element_symbol, ion_number_string = re.match('^(\w+)\s*(\d+)', species_string).groups()
    except AttributeError:
        try:
            element_symbol, ion_number_string = species_string.split()
        except ValueError:
            raise MalformedSpeciesError('Species string "{0}" is not of format <element_symbol><number> '
                                        '(e.g. Fe 2, Fe2, ..)'.format(species_string))

    atomic_number = element_symbol2atomic_number(element_symbol)

    try:
        ion_number = roman_to_int(ion_number_string)
    except ValueError:
        try:
            ion_number = int(ion_number_string)
        except ValueError:
            raise MalformedSpeciesError("Given ion number ('{}') could not be parsed ".format(ion_number_string))

    if ion_number > atomic_number:
        raise ValueError('Species given does not exist: ion number > atomic number')

    return atomic_number, ion_number - 1


def parse_quantity(quantity_string):

    if not isinstance(quantity_string, basestring):
        raise MalformedQuantityError(quantity_string)

    try:
        value_string, unit_string = quantity_string.split()
    except ValueError:
        raise MalformedQuantityError(quantity_string)

    try:
        value = float(value_string)
    except ValueError:
        raise MalformedQuantityError(quantity_string)

    try:
        q = u.Quantity(value, unit_string)
    except ValueError:
        raise MalformedQuantityError(quantity_string)

    return q


def element_symbol2atomic_number(element_string):
    reformatted_element_string = reformat_element_symbol(element_string)
    if reformatted_element_string not in symbol2atomic_number:
        raise MalformedElementSymbolError(element_string)
    return symbol2atomic_number[reformatted_element_string]

def atomic_number2element_symbol(atomic_number):
    """
    Convert atomic number to string symbol
    """
    return atomic_number2symbol[atomic_number]

def reformat_element_symbol(element_string):
    """
    Reformat the string so the first letter is uppercase and all subsequent letters lowercase

    Parameters
    ----------
        element_symbol: str

    Returns
    -------
        reformated element symbol
    """

    return element_string[0].upper() + element_string[1:].lower()


def quantity_linspace(start, stop, num, **kwargs):
    """
    Calculate the linspace for a quantity start and stop.
    Other than that essentially the same input parameters as linspace

    Parameters
    ----------
    start: ~astropy.Quantity
    stop: ~astropy.Quantity
    num: ~int

    Returns
    -------
        : ~astropy.Quantity


    """
    if not (hasattr(start, 'unit') and hasattr(stop, 'unit')):
        raise ValueError('Both start and stop need to be quantities with a '
                         'unit attribute')

    return np.linspace(start.value, stop.to(start.unit).value, num, **kwargs) * start.unit


def convert_abundances_format(fname, delimiter='\s+'):
    df = pd.read_csv(fname, delimiter=delimiter, comment='#', header=None)
    #Drop shell index column
    df.drop(df.columns[0], axis=1, inplace=True)
    #Assign header row
    df.columns = [nucname.name(i)
                  for i in range(1, df.shape[1] + 1)]
    return df
