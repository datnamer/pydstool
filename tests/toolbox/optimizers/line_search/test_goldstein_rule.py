#/usr/bin/env python

# Matthieu Brucher
# Last Change : 2007-08-22 14:01

from __future__ import absolute_import

import unittest
import numpy

from PyDSTool.Toolbox.optimizers.line_search import GoldsteinRule


class Function(object):
  def __call__(self, x):
    return (x[0] - 2) ** 3 + (2 * x[1] + 4) ** 2

  def gradient(self, x):
    return numpy.array((3 * (x[0] - 2) ** 2, 4 * (2 * x[1] + 4)))

class test_GoldsteinRuleSearch(unittest.TestCase):
  def test_call_gradient_direction(self):
    lineSearch = GoldsteinRule()
    state = {'gradient' : numpy.array((12., 16.)), 'direction' : numpy.array((4., -8.))}
    function = Function()
    x = lineSearch(origin = numpy.zeros((2)), state = state, function = function)
    assert(function(x) <= function(numpy.zeros((2))) + 0.1 * state['alpha_step'] * numpy.dot(numpy.array((12., 16.)), numpy.array((4., -8.))))
    assert(function(x) >= function(numpy.zeros((2))) + 0.9 * state['alpha_step'] * numpy.dot(numpy.array((12., 16.)), numpy.array((4., -8.))))
    assert(state['alpha_step'] > 0)

if __name__ == "__main__":
  unittest.main()
