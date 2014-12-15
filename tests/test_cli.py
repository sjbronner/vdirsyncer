# -*- coding: utf-8 -*-
'''
    tests.test_cli
    ~~~~~~~~~~~~~~

    :copyright: (c) 2014 Markus Unterwaditzer & contributors
    :license: MIT, see LICENSE for more details.
'''
import io
from textwrap import dedent

from click.testing import CliRunner

import pytest

import vdirsyncer.cli as cli


def test_load_config(monkeypatch):
    f = io.StringIO(dedent(u'''
        [general]
        status_path = /tmp/status/

        [pair bob]
        a = bob_a
        b = bob_b
        foo = bar
        bam = true

        [storage bob_a]
        type = filesystem
        path = /tmp/contacts/
        fileext = .vcf
        yesno = off
        number = 42

        [storage bob_b]
        type = carddav

        [bogus]
        lol = true
        '''))

    errors = []
    monkeypatch.setattr('vdirsyncer.cli.cli_logger.error', errors.append)
    general, pairs, storages = cli.load_config(f, pair_options=('bam',))
    assert general == {'status_path': '/tmp/status/'}
    assert pairs == {'bob': ('bob_a', 'bob_b', {'bam': True}, {'foo': 'bar'})}
    assert storages == {
        'bob_a': {'type': 'filesystem', 'path': '/tmp/contacts/', 'fileext':
                  '.vcf', 'yesno': False, 'number': 42,
                  'instance_name': 'bob_a'},
        'bob_b': {'type': 'carddav', 'instance_name': 'bob_b'}
    }

    assert len(errors) == 1
    assert errors[0].startswith('Unknown section')
    assert 'bogus' in errors[0]


def test_storage_instance_from_config(monkeypatch):
    def lol(**kw):
        assert kw == {'foo': 'bar', 'baz': 1}
        return 'OK'

    import vdirsyncer.storage
    monkeypatch.setitem(vdirsyncer.storage.storage_names, 'lol', lol)
    config = {'type': 'lol', 'foo': 'bar', 'baz': 1}
    assert cli.storage_instance_from_config(config) == 'OK'


def test_parse_pairs_args():
    pairs = {
        'foo': ('bar', 'baz', {'conflict_resolution': 'a wins'},
                {'storage_option': True}),
        'one': ('two', 'three', {'collections': 'a,b,c'}, {}),
        'eins': ('zwei', 'drei', {'ha': True}, {})
    }
    assert sorted(
        cli.parse_pairs_args(['foo/foocoll', 'one', 'eins'], pairs)
    ) == [
        ('eins', None),
        ('foo', 'foocoll'),
        ('one', 'a'),
        ('one', 'b'),
        ('one', 'c')
    ]


def test_simple_run(tmpdir):
    config_file = tmpdir.join('config')
    config_file.write(dedent('''
    [general]
    status_path = {0}/status/

    [pair my_pair]
    a = my_a
    b = my_b

    [storage my_a]
    type = filesystem
    path = {0}/path_a/
    fileext = .txt

    [storage my_b]
    type = filesystem
    path = {0}/path_b/
    fileext = .txt
    ''').format(str(tmpdir)))

    runner = CliRunner(env={'VDIRSYNCER_CONFIG': str(config_file)})
    result = runner.invoke(cli.app, ['sync'])
    assert not result.exception
    assert result.output.lower().strip() == 'syncing my_pair'

    tmpdir.join('path_a/haha.txt').write('UID:haha')
    result = runner.invoke(cli.app, ['sync'])
    assert result.output == ('Syncing my_pair\n'
                             'Copying (uploading) item haha to my_b\n')
    assert tmpdir.join('path_b/haha.txt').read() == 'UID:haha'

    result = runner.invoke(cli.app, ['sync', 'my_pair', 'my_pair'])
    assert set(result.output.splitlines()) == set([
        'Syncing my_pair',
        'warning: Already prepared my_pair, skipping'
    ])
    assert not result.exception


def test_empty_storage(tmpdir):
    config_file = tmpdir.join('config')
    config_file.write(dedent('''
    [general]
    status_path = {0}/status/

    [pair my_pair]
    a = my_a
    b = my_b

    [storage my_a]
    type = filesystem
    path = {0}/path_a/
    fileext = .txt

    [storage my_b]
    type = filesystem
    path = {0}/path_b/
    fileext = .txt
    ''').format(str(tmpdir)))

    runner = CliRunner(env={'VDIRSYNCER_CONFIG': str(config_file)})
    result = runner.invoke(cli.app, ['sync'])
    assert not result.exception
    assert result.output.lower().strip() == 'syncing my_pair'

    tmpdir.join('path_a/haha.txt').write('UID:haha')
    result = runner.invoke(cli.app, ['sync'])
    tmpdir.join('path_b/haha.txt').remove()
    result = runner.invoke(cli.app, ['sync'])
    lines = result.output.splitlines()
    assert len(lines) == 2
    assert lines[0] == 'Syncing my_pair'
    assert lines[1].startswith('error: my_pair: '
                               'Storage "my_b" was completely emptied.')
    assert result.exception


def test_missing_general_section(tmpdir):
    config_file = tmpdir.join('config')
    config_file.write(dedent('''
    [pair my_pair]
    a = my_a
    b = my_b

    [storage my_a]
    type = filesystem
    path = {0}/path_a/
    fileext = .txt

    [storage my_b]
    type = filesystem
    path = {0}/path_b/
    fileext = .txt
    ''').format(str(tmpdir)))

    runner = CliRunner()
    result = runner.invoke(
        cli.app, ['sync'],
        env={'VDIRSYNCER_CONFIG': str(config_file)}
    )
    assert result.exception
    assert result.output.startswith('critical:')
    assert 'unable to find general section' in result.output.lower()


def test_wrong_general_section(tmpdir):
    config_file = tmpdir.join('config')
    config_file.write(dedent('''
    [general]
    wrong = true
    '''))

    runner = CliRunner()
    result = runner.invoke(
        cli.app, ['sync'],
        env={'VDIRSYNCER_CONFIG': str(config_file)}
    )

    assert result.exception
    lines = result.output.splitlines()
    assert lines[:-1] == [
        'critical: general section doesn\'t take the parameters: wrong',
        'critical: general section is missing the parameters: status_path'
    ]
    assert lines[-1].startswith('critical:')
    assert lines[-1].endswith('Invalid general section.')


def test_verbosity(tmpdir):
    runner = CliRunner()
    config_file = tmpdir.join('config')
    config_file.write(dedent('''
    [general]
    status_path = {0}/status/
    ''').format(str(tmpdir)))

    result = runner.invoke(
        cli.app, ['--verbosity=HAHA', 'sync'],
        env={'VDIRSYNCER_CONFIG': str(config_file)}
    )
    assert result.exception
    assert 'invalid verbosity value' in result.output.lower()


def test_invalid_storage_name():
    f = io.StringIO(dedent(u'''
        [general]
        status_path = /tmp/status/

        [storage foo.bar]
        '''))

    with pytest.raises(cli.CliError) as excinfo:
        cli.load_config(f)

    assert 'invalid characters' in str(excinfo.value).lower()
