from testtools import TestCase
# from testtools import skip
import fixtures
import textwrap
from ConfigParser import ConfigParser
from StringIO import StringIO
import csv_to_psql.main as m
import subprocess


class Test_parse_args(TestCase):

    def test_table_name(self):
        args = m.parse_args(['test.table'])
        self.assertEquals('test.table', args.table_name)

    def test_table_name_is_mandatory(self):
        fixture = self.useFixture(fixtures.StringStream('stderr'))
        with fixtures.MonkeyPatch('sys.stderr', fixture.stream):
            self.assertRaises(SystemExit, m.parse_args, [])

    def test_option_create_table(self):
        args = m.parse_args('test.table --create-table'.split())
        self.assertTrue(args.create_table)

    def test_option_create_table_defaults_to_false(self):
        args = m.parse_args(['test.table'])
        self.assertFalse(args.create_table)

    def test_primary_key(self):
        args = m.parse_args('x --primary-key=a,b'.split())
        self.assertEqual(['a', 'b'], args.primary_key)

    def test_primary_key_defaults_to_empty_list(self):
        args = m.parse_args('test.table'.split())
        self.assertEqual([], args.primary_key)

    def test_field_meta(self):
        args = m.parse_args('test.table --fields-meta=fields.ini'.split())
        self.assertEqual('fields.ini', args.fields_meta)

    def test_field_meta_defaults_to_None(self):
        args = m.parse_args('test.table'.split())
        self.assertIsNone(args.fields_meta)

    def test_all_parameters(self):
        argv = [
            'test_table',
            '--create-table',
            '--primary-key=pkfield',
            '--fields=somedef.ini',
        ]
        args = m.parse_args(argv)
        self.assertEquals('test_table', args.table_name)
        self.assertTrue(args.create_table)
        self.assertEqual(['pkfield'], args.primary_key)
        self.assertEqual('somedef.ini', args.fields_meta)


def get_fields_meta(ini_content):
    fake_file = StringIO(textwrap.dedent(ini_content))
    config = ConfigParser()
    config.readfp(fake_file)
    return m.FieldsMeta(config)


class Test_TableMeta(TestCase):

    def test_fields(self):
        meta = get_fields_meta(
            '''\
            [field:a]
            [field:x]
            ''')
        self.assertEqual(['a', 'x'], meta.fields)

    def test_get_type(self):
        meta = get_fields_meta(
            '''\
            [field:a]
            type: a-type
            [field:x]
            type: what-type?
            ''')
        self.assertEqual('a-type', meta.get_type('a'))
        self.assertEqual('what-type?', meta.get_type('x'))

    def test_get_type_defaults_to_VARCHAR(self):
        meta = get_fields_meta('')
        self.assertEqual('VARCHAR', meta.get_type('a_field'))

    def test_get_type_inherited_from_DEFAULT(self):
        meta = get_fields_meta(
            '''\
            [DEFAULT]
            type: default-type
            ''')
        self.assertEqual('default-type', meta.get_type('a'))

    def test_is_nullable(self):
        meta = get_fields_meta(
            '''\
            [field:a_field]
            nullable: false
            ''')
        self.assertFalse(meta.is_nullable('a_field'))

    def test_is_nullable_defaults_to_true(self):
        meta = get_fields_meta('')
        self.assertTrue(meta.is_nullable('a_field'))

    def test_is_nullable_inherited_from_DEFAULT(self):
        meta = get_fields_meta(
            '''\
            [DEFAULT]
            nullable: false
            ''')
        self.assertFalse(meta.is_nullable('a_field'))

    def test_invalid_config_is_nullable_raises_exception(self):
        meta = get_fields_meta(
            '''\
            [DEFAULT]
            nullable: sure
            ''')
        self.assertRaises(m.ConfigurationError, meta.is_nullable, 'a_field')

    def test__get_value_missing_value_in_section_inherits_from_DEFAULT(self):
        meta = get_fields_meta(
            '''\
            [DEFAULT]
            not_in_a: value4notina
            [field:a]
            type: int
            ''')
        self.assertEqual(
            'value4notina',
            meta._get_value('a', 'not_in_a', 'default'))


class Test_create_table(TestCase):

    def test_defaults_without_primary_keys(self):
        sql = m.create_table(
            table_name='mistery',
            field_names='csv header fields'.split(),
            fields_meta=get_fields_meta(''),
            primary_key_fields=[])

        self.assertIn('CREATE TABLE mistery(', sql)
        self.assertIn('    csv VARCHAR,', sql)
        self.assertIn('    header VARCHAR,', sql)
        self.assertIn('    fields VARCHAR', sql)

    def test_unknown_field_in_primary_keys_is_an_error(self):
        self.assertRaises(
            m.FieldsNotInInput,
            m.create_table,
            table_name='mistery',
            field_names='csv header fields'.split(),
            fields_meta=get_fields_meta(''),
            primary_key_fields=['extra-field'])

    def test_type_nullable_primary_key_attributes_are_respected(self):
        sql = m.create_table(
            table_name='all_in_one',
            field_names='a b c'.split(),
            fields_meta=get_fields_meta(
                '''\
                [DEFAULT]
                type: integer
                nullable: false

                [field:b]
                nullable: true

                [field:c]
                type: media
                '''),
            primary_key_fields=['a', 'c'])

        self.assertIn('CREATE TABLE all_in_one(', sql)
        self.assertIn('    a integer NOT NULL,', sql)
        self.assertIn('    b integer,', sql)
        self.assertIn('    c media NOT NULL,', sql)
        self.assertIn('    PRIMARY KEY (a, c)', sql)


import os
import tempfile


class File(fixtures.Fixture):

    def __init__(self, content):
        self.content = content
        self.path = None

    def setUp(self):
        super(File, self).setUp()
        fd, self.path = tempfile.mkstemp()
        self.addCleanup(os.remove, self.path)
        try:
            os.write(fd, self.content)
        finally:
            os.close(fd)


TEST_CSV = '''\
a,b,c
1,2,3
4,5,6
'''

TEST_FIELDS_META = b'''\
[field:a]
nullable: false

[field:b]
type: qwertype
'''


class Test_main(TestCase):

    def call_main(self, argv, stdin):
        stdout = StringIO()
        m.main(argv, StringIO(stdin), stdout)
        return stdout.getvalue().replace('\r', '')

    def test_input_is_duplicated_in_output(self):
        stdout = self.call_main(['MAGIC.tablename'], TEST_CSV)
        self.assertIn(TEST_CSV, stdout)

    def test_fields_meta_is_read(self):
        fields_meta = self.useFixture(File(TEST_FIELDS_META))

        argv = [
            'MAGIC.tablename',
            '--create-table',
            '--fields-meta=' + fields_meta.path]
        stdout = self.call_main(argv, TEST_CSV)

        self.assertIn('qwertype', stdout)

    def test_null_values_on_import_are_allowed_by_default(self):
        stdout = self.call_main(['MAGIC.tablename'], TEST_CSV)
        self.assertNotIn('force not null', stdout)

    def test_null_values_can_be_avoided_by_defining_fields_non_nullable(self):
        fields_meta = self.useFixture(File(TEST_FIELDS_META))

        argv = [
            'MAGIC.tablename',
            '--fields-meta=' + fields_meta.path]
        stdout = self.call_main(argv, TEST_CSV)

        self.assertIn('force not null', stdout)


class Test_script_csv_to_postgres(TestCase):

    def test(self):
        # Note, that this test does not mean
        # that the script will properly import into postgres:
        # integration with postgres's psql is not covered

        fields_meta = self.useFixture(File(TEST_FIELDS_META))
        stdin_file = self.useFixture(File(TEST_CSV.encode('utf8')))

        argv = [
            'csv_to_psql',
            'MAGIC.tablename',
            '--create-table',
            '--fields-meta=' + fields_meta.path]
        with open(stdin_file.path) as stdin:
            stdout = subprocess.check_output(argv, stdin=stdin).decode('utf8')

        self.assertIn('CREATE TABLE MAGIC.tablename', stdout)
        self.assertIn('qwertype', stdout)
        self.assertIn(TEST_CSV, stdout.replace('\r', ''))
