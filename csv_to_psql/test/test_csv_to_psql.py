from testtools import TestCase, skip
import fixtures
import textwrap
from ConfigParser import ConfigParser
from StringIO import StringIO
import csv_to_psql.main as m

# empty test to warn developers about untested code when running tox/coverage

__all__ = ['m']


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


TEST_CSV = '''\
a,b,c
1,2,3
4,5,6
'''


class Test_main(TestCase):

    def call(self, argv, stdin):
        stdout = StringIO()
        m.main(argv, StringIO(stdin), stdout)
        return stdout.getvalue().replace('\r', '')

    def test_input_is_duplicated_in_output(self):
        stdout = self.call(['MAGIC.tablename'], TEST_CSV)
        self.assertIn(TEST_CSV, stdout)
        self.assertNotIn('force not null', stdout)

    @skip('Work in progress - see tox output for missing coverage')
    def test_fields_meta_is_read(self):
        self.useFixture()
        stdout = self.call(['MAGIC.tablename'], TEST_CSV)
        self.assertIn(TEST_CSV, stdout)
        self.assertNotIn('force not null', stdout)
