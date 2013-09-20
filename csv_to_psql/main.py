'''
Convert CSV input on STDIN to a psql script on STDOUT that imports it

Usage:
    csv_to_psql [options] name-of-table-to-create < file.csv | psql
'''

import csv
import sys
import argparse
from ConfigParser import ConfigParser


class ConfigurationError(Exception):
    ''' I am to notify the user that
    the fields-meta file is not correct '''


class FieldsNotInInput(Exception):
    ''' I am to notify the user that
    field name[s] was specified which is not in the input '''


def parse_args(argv):
    ''' I am parsing the command line parameters '''
    parser = argparse.ArgumentParser()
    parser.add_argument('table_name')

    parser.add_argument('--create-table', action='store_true')

    def split_on_comma(arg):
        return arg.split(',')
    parser.add_argument(
        '--primary-key', action='store', default=[], type=split_on_comma)

    parser.add_argument(
        '--fields-meta', '--fields', action='store')

    parser.add_argument(
        '--param', dest='params', default=[], action='append', nargs=2)

    return parser.parse_args(argv)


class FieldsMeta(object):

    ''' I provide easy access to fields-meta settings '''

    FIELD_PREFIX = 'field:'
    KEY_TYPE = 'type'
    KEY_NULLABLE = 'nullable'

    def __init__(self, config, params):
        self.config = config
        self.params = params

    @property
    def fields(self):
        FIELD_PREFIX = self.FIELD_PREFIX
        return [
            section[len(FIELD_PREFIX):]
            for section in self.config.sections()
            if section.startswith(FIELD_PREFIX)]

    def _get_value(self, field, key, default):
        field_section = self.FIELD_PREFIX + field

        if self.config.has_option(field_section, key):
            return self.config.get(field_section, key, vars=self.params)

        return self.config.defaults().get(key, default)

    def get_type(self, field):
        return self._get_value(field, self.KEY_TYPE, 'VARCHAR')

    def is_nullable(self, field):
        value = self._get_value(field, self.KEY_NULLABLE, 'true')

        if value.lower() not in {'true', 'false'}:
            raise ConfigurationError(
                'Invalid value [{}{}] nullable: {}'
                .format(self.FIELD_PREFIX, field, value))

        return value.lower() == 'true'


CREATE_TABLE_TEMPLATE = '''
CREATE TABLE {table}(
    {fielddefs_and_constraints}
);
'''


def create_table(table_name, field_names, fields_meta, primary_key_fields):
    if set(primary_key_fields) - set(field_names):
        raise FieldsNotInInput(set(primary_key_fields) - set(field_names))

    def field_def(field):
        nullable = fields_meta.is_nullable(field)
        return (
            '{field} {type}{notnull}'
            .format(
                field=field,
                type=fields_meta.get_type(field),
                notnull='' if nullable else ' NOT NULL'))

    fielddefs = [field_def(field) for field in field_names]

    if primary_key_fields:
        primary_key_constraint = [
            'PRIMARY KEY ({})'.format(', '.join(primary_key_fields))
            ]
    else:
        primary_key_constraint = []

    return CREATE_TABLE_TEMPLATE.format(
        table=table_name,
        fielddefs_and_constraints=',\n    '.join(
            fielddefs + primary_key_constraint))


SQL_TEMPLATE = '''\
-- exit on any error, to prevent damage
\\set ON_ERROR_STOP on
{create_table}
\\copy {table}({columns}) from stdin with csv header {notnullclause}
'''


def main(argv=sys.argv[1:], stdin=sys.stdin, stdout=sys.stdout):
    args = parse_args(argv)

    fields_ini = ConfigParser()
    if args.fields_meta:
        fields_ini.read(args.fields_meta)
    fields_meta = FieldsMeta(fields_ini, dict(args.params))

    reader = iter(csv.reader(stdin))
    header = reader.next()

    notnullcolumns = [
        field
        for field in header
        if not fields_meta.is_nullable(field)]

    create_table_sql = ''
    if args.create_table:
        create_table_sql = create_table(
            args.table_name, header, fields_meta, args.primary_key)

    notnullclause = ''
    if notnullcolumns:
        notnullclause = 'force not null ' + ', '.join(notnullcolumns)

    create_and_import_sql = SQL_TEMPLATE.format(
        create_table=create_table_sql,
        table=args.table_name,
        columns=', '.join(header),
        notnullclause=notnullclause)

    stdout.write(create_and_import_sql)

    writer = csv.writer(stdout)
    writer.writerow(header)
    writer.writerows(reader)


if __name__ == '__main__':
    # tested, see Test_script_csv_to_postgres.test
    main()  # pragma: nocover
