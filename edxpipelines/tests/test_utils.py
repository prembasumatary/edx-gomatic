import mock
import unittest

from ddt import ddt, data, unpack
import edxpipelines.utils as util


@ddt
class TestDictMerge(unittest.TestCase):

    @data(({'key1': "value1", "key2": "value2"}, {'key1': "value1"}, {'key2': "value2"}),
          ({'key1': "value1", "key2": "value2", "key3": "value3", "key4": "value4"}, {'key1': "value1"}, {'key2': "value2"}, {'key3': "value3"}, {'key4': "value4"}),
          ({"key1": {"nested_key1": "nested_value2", "nested_key2": "nested_value2"}}, {"key1": {"nested_key1": "nested_value2"}}, {"key1": {"nested_key2": "nested_value2"}}),
          ({"key1": {"nested_key1": {"nested_key2": "nested_value2", "nested_key3": "nested_value3"}}}, {"key1": {"nested_key1": {"nested_key2": "nested_value2"}}}, {"key1": {"nested_key1": {"nested_key3": "nested_value3"}}})
          )
    @unpack
    def test_merge(self, expected, *args):
        self.assertEqual(util.dict_merge(*args), expected)

    @data(({'key1': "value1"}, {'key1': "value2"}),
          ({'key1': {'key11': "value11"} }, {'key1': {'key11': "value22"}}),
          ({'key1': ['key11', "value11"]}, {'key1': {'key11': "value22"}}),
          ({'key1': ['key11', "value11"]}, {'key1': ['key11', "value12"]})
          )
    @unpack
    def test_merge_collision(self, *args):
        self.assertRaises(util.MergeConflict, util.dict_merge, *args)

    @data(("edxpipelines/tests/variables1.yml", {'key1': 'value1', 'key2': 'value2', 'key3': 'value3'}))
    @unpack
    def test_load_yaml_from_file(self, file_path, expected):
        variables = util.load_yaml_from_file(file_path)
        for key, val in expected.iteritems():
            self.assertEqual(variables[key], val)
