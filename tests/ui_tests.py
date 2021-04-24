"""Tests for the user interface."""
#
# (C) Pywikibot team, 2008-2021
#
# Distributed under the terms of the MIT license.
#
# NOTE FOR RUNNING WINDOWS UI TESTS
#
# Windows UI tests have to be run using the tests\ui_tests.bat helper script.
# This will set PYTHONPATH and PYWIKIBOT_DIR, and then run the tests. Do not
# touch mouse or keyboard while the tests are running, as this might disturb
# the interaction tests.
#
# The Windows tests were developed on a Dutch Windows 7 OS. You might need to
# adapt the helper functions in TestWindowsTerminalUnicode for other versions.
#
# For the Windows-based tests, you need the following packages installed:
#   - pywin32, for clipboard access, which can be installed using:
#     pip install -U pywin32
#
#   - pywinauto, to send keys to the terminal, which can be installed using:
#     pip install -U pywinauto
#
#
import inspect
import io
import logging
import os
import subprocess
import sys
import time

from contextlib import suppress

import pywikibot

from tests.aspects import TestCase, TestCaseBase
from tests.utils import unittest, FakeModule

from pywikibot.bot import (
    CRITICAL,
    DEBUG,
    ERROR,
    INFO,
    INPUT,
    STDOUT,
    ui,
    VERBOSE,
    WARNING,
)

from pywikibot.userinterfaces import (
    terminal_interface_base,
    terminal_interface_unix,
    terminal_interface_win32,
)

if os.name == 'nt':
    from multiprocessing.managers import BaseManager
    import threading

    try:
        import win32api
    except ImportError:
        win32api = None

    try:
        import pywinauto
    except ImportError:
        pywinauto = None

    try:
        import win32clipboard
    except ImportError:
        win32clipboard = None


class Stream:

    """Handler for a StringIO or BytesIO instance able to patch itself."""

    def __init__(self, name: str, patched_streams: dict):
        """
        Create a new stream with a StringIO or BytesIO instance.

        @param name: The part after 'std' (e.g. 'err').
        @param patched_streams: A mapping which maps the original stream to
            the patched stream.
        """
        self._stream = io.StringIO()
        self._name = 'std{0}'.format(name)
        self._original = getattr(sys, self._name)
        patched_streams[self._original] = self._stream

    def __repr__(self):
        return '<patched {} {!r} wrapping {!r}>'.format(
            self._name, self._stream, self._original)

    def reset(self):
        """Reset own stream."""
        self._stream.truncate(0)
        self._stream.seek(0)


if os.name == 'nt':

    class pywikibotWrapper:

        """pywikibot wrapper class."""

        def init(self):
            pywikibot.version._get_program_dir()

        def output(self, *args, **kwargs):
            return pywikibot.output(*args, **kwargs)

        def request_input(self, *args, **kwargs):
            self.input = None

            def threadedinput():
                self.input = pywikibot.input(*args, **kwargs)
            self.inputthread = threading.Thread(target=threadedinput)
            self.inputthread.start()

        def get_input(self):
            self.inputthread.join()
            return self.input

        def set_config(self, key, value):
            setattr(pywikibot.config, key, value)

        def set_ui(self, key, value):
            setattr(pywikibot.ui, key, value)

        def cls(self):
            subprocess.run('cls', shell=True)

    class pywikibotManager(BaseManager):

        """pywikibot manager class."""

        pass

    pywikibotManager.register('pywikibot', pywikibotWrapper)
    _manager = pywikibotManager(
        address=('127.0.0.1', 47228),
        authkey=b'4DJSchgwy5L5JxueZEWbxyeG')
    if len(sys.argv) > 1 and sys.argv[1] == '--run-as-slave-interpreter':
        s = _manager.get_server()
        s.serve_forever()


def patched_print(text, target_stream):
    try:
        stream = patched_streams[target_stream]
    except KeyError:
        assert isinstance(target_stream,
                          pywikibot.userinterfaces.win32_unicode.UnicodeOutput)
        assert target_stream._stream
        stream = patched_streams[target_stream._stream]
    org_print(text, stream)


def patched_input():
    return strin._stream.readline().strip()


patched_streams = {}
strout = Stream('out', patched_streams)
strerr = Stream('err', patched_streams)
strin = Stream('in', {})

newstdout = strout._stream
newstderr = strerr._stream
newstdin = strin._stream

org_print = ui._print
org_input = ui._raw_input


def patch():
    """Patch standard terminal files."""
    strout.reset()
    strerr.reset()
    strin.reset()
    ui._print = patched_print
    ui._raw_input = patched_input


def unpatch():
    """Un-patch standard terminal files."""
    ui._print = org_print
    ui._raw_input = org_input


logger = logging.getLogger('pywiki')
loggingcontext = {'caller_name': 'ui_tests',
                  'caller_file': 'ui_tests',
                  'caller_line': 0,
                  'newline': '\n'}


class UITestCase(TestCaseBase):

    """UI tests."""

    net = False

    def setUp(self):
        super().setUp()
        patch()

        pywikibot.config.colorized_output = True
        pywikibot.config.transliterate = False
        pywikibot.ui.transliteration_target = None
        pywikibot.ui.encoding = 'utf-8'

    def tearDown(self):
        super().tearDown()
        unpatch()


class TestTerminalOutput(UITestCase):

    """Terminal output tests."""

    tests = [
        ('debug', DEBUG, '', ''),
        ('verbose', VERBOSE, '', ''),
        ('info', INFO, '', 'info\n'),
        ('stdout', STDOUT, 'stdout\n', ''),
        ('input', INPUT, '', 'input\n'),
        ('WARNING', WARNING, '', 'WARNING: WARNING\n'),
        ('ERROR', ERROR, '', 'ERROR: ERROR\n'),
        ('CRITICAL', CRITICAL, '', 'CRITICAL: CRITICAL\n'),
    ]

    def test_outputlevels_logging(self):
        """Test logger with output levels."""
        for text, level, out, err in self.tests:
            with self.subTest(test=text):
                logger.log(level, text, extra=loggingcontext)
                self.assertEqual(newstdout.getvalue(), out)
                self.assertEqual(newstderr.getvalue(), err)
                patch()  # reset terminal files

    def test_output(self):
        pywikibot.output('output')
        self.assertEqual(newstdout.getvalue(), '')
        self.assertEqual(newstderr.getvalue(), 'output\n')

    def test_stdout(self):
        pywikibot.stdout('output')
        self.assertEqual(newstdout.getvalue(), 'output\n')
        self.assertEqual(newstderr.getvalue(), '')

    def test_warning(self):
        pywikibot.warning('warning')
        self.assertEqual(newstdout.getvalue(), '')
        self.assertEqual(newstderr.getvalue(), 'WARNING: warning\n')

    def test_error(self):
        pywikibot.error('error')
        self.assertEqual(newstdout.getvalue(), '')
        self.assertEqual(newstderr.getvalue(), 'ERROR: error\n')

    def test_log(self):
        pywikibot.log('log')
        self.assertEqual(newstdout.getvalue(), '')
        self.assertEqual(newstderr.getvalue(), '')

    def test_critical(self):
        pywikibot.critical('critical')
        self.assertEqual(newstdout.getvalue(), '')
        self.assertEqual(newstderr.getvalue(), 'CRITICAL: critical\n')

    def test_debug(self):
        pywikibot.debug('debug', 'test')
        self.assertEqual(newstdout.getvalue(), '')
        self.assertEqual(newstderr.getvalue(), '')

    def test_exception(self):
        class TestException(Exception):

            """Test exception."""

        try:
            raise TestException('Testing Exception')
        except TestException:
            pywikibot.exception('exception')
        self.assertEqual(newstdout.getvalue(), '')
        self.assertEqual(newstderr.getvalue(),
                         'ERROR: TestException: Testing Exception\n')

    def test_exception_tb(self):
        class TestException(Exception):

            """Test exception."""

        try:
            raise TestException('Testing Exception')
        except TestException:
            pywikibot.exception('exception', tb=True)
        self.assertEqual(newstdout.getvalue(), '')
        stderrlines = newstderr.getvalue().split('\n')
        self.assertEqual(stderrlines[0],
                         'ERROR: TestException: Testing Exception')
        self.assertEqual(stderrlines[1], 'Traceback (most recent call last):')
        self.assertEqual(stderrlines[3],
                         "    raise TestException('Testing Exception')")
        self.assertTrue(stderrlines[4].endswith(': Testing Exception'))

        self.assertNotEqual(stderrlines[-1], '\n')


class TestTerminalInput(UITestCase):

    """Terminal input tests."""

    input_choice_output = 'question ([A]nswer 1, a[n]swer 2, an[s]wer 3): '

    def testInput(self):
        newstdin.write('input to read\n')
        newstdin.seek(0)
        returned = pywikibot.input('question')

        self.assertEqual(newstdout.getvalue(), '')
        self.assertEqual(newstderr.getvalue(), 'question: ')
        self.assertIsInstance(returned, str)
        self.assertEqual(returned, 'input to read')

    def test_input_yn(self):
        newstdin.write('\n')
        newstdin.seek(0)
        returned = pywikibot.input_yn('question', False, automatic_quit=False)

        self.assertEqual(newstdout.getvalue(), '')
        self.assertEqual(newstderr.getvalue(), 'question ([y]es, [N]o): ')
        self.assertFalse(returned)

    def _call_input_choice(self):
        rv = pywikibot.input_choice(
            'question',
            (('answer 1', 'A'),
             ('answer 2', 'N'),
             ('answer 3', 'S')),
            'A',
            automatic_quit=False)

        self.assertEqual(newstdout.getvalue(), '')
        self.assertIsInstance(rv, str)
        return rv

    def testInputChoiceDefault(self):
        newstdin.write('\n')
        newstdin.seek(0)
        returned = self._call_input_choice()

        self.assertEqual(returned, 'a')

    def testInputChoiceCapital(self):
        newstdin.write('N\n')
        newstdin.seek(0)
        returned = self._call_input_choice()

        self.assertEqual(newstderr.getvalue(), self.input_choice_output)
        self.assertEqual(returned, 'n')

    def testInputChoiceNonCapital(self):
        newstdin.write('n\n')
        newstdin.seek(0)
        returned = self._call_input_choice()

        self.assertEqual(newstderr.getvalue(), self.input_choice_output)
        self.assertEqual(returned, 'n')

    def testInputChoiceIncorrectAnswer(self):
        newstdin.write('X\nN\n')
        newstdin.seek(0)
        returned = self._call_input_choice()

        self.assertEqual(newstderr.getvalue(), self.input_choice_output * 2)
        self.assertEqual(returned, 'n')


@unittest.skipUnless(os.name == 'posix', 'requires Unix console')
class TestTerminalOutputColorUnix(UITestCase):

    """Terminal output color tests."""

    str1 = 'text \03{lightpurple}light purple text\03{default} text'

    def testOutputColorizedText(self):
        pywikibot.output(self.str1)
        self.assertEqual(newstdout.getvalue(), '')
        self.assertEqual(
            newstderr.getvalue(),
            'text \x1b[95mlight purple text\x1b[0m text\n')

    def testOutputNoncolorizedText(self):
        pywikibot.config.colorized_output = False
        pywikibot.output(self.str1)
        self.assertEqual(newstdout.getvalue(), '')
        self.assertEqual(
            newstderr.getvalue(),
            'text light purple text text ***\n')

    str2 = ('normal text \03{lightpurple} light purple '
            '\03{lightblue} light blue \03{previous} light purple '
            '\03{default} normal text')

    def testOutputColorCascade_incorrect(self):
        """Test incorrect behavior of testOutputColorCascade."""
        pywikibot.output(self.str2)
        self.assertEqual(newstdout.getvalue(), '')
        self.assertEqual(
            newstderr.getvalue(),
            'normal text \x1b[95m light purple '
            '\x1b[94m light blue \x1b[95m light purple '
            '\x1b[0m normal text\n')


@unittest.skipUnless(os.name == 'posix', 'requires Unix console')
class TestTerminalUnicodeUnix(UITestCase):

    """Terminal output tests for unix."""

    def testOutputUnicodeText(self):
        pywikibot.output('Заглавная_страница')
        self.assertEqual(newstdout.getvalue(), '')
        self.assertEqual(newstderr.getvalue(), 'Заглавная_страница\n')

    def testInputUnicodeText(self):
        newstdin.write('Заглавная_страница\n')
        newstdin.seek(0)

        returned = pywikibot.input('Википедию? ')

        self.assertEqual(newstdout.getvalue(), '')
        self.assertEqual(
            newstderr.getvalue(), 'Википедию? ')

        self.assertIsInstance(returned, str)
        self.assertEqual(returned, 'Заглавная_страница')


@unittest.skipUnless(os.name == 'posix', 'requires Unix console')
class TestTransliterationUnix(UITestCase):

    """Terminal output transliteration tests."""

    def testOutputTransliteratedUnicodeText(self):
        pywikibot.ui.encoding = 'latin-1'
        pywikibot.config.transliterate = True
        pywikibot.output('abcd АБГД αβγδ あいうえお')
        self.assertEqual(newstdout.getvalue(), '')
        self.assertEqual(
            newstderr.getvalue(),
            'abcd \x1b[93mA\x1b[0m\x1b[93mB\x1b[0m\x1b[93mG\x1b[0m'
            '\x1b[93mD\x1b[0m \x1b[93ma\x1b[0m\x1b[93mb\x1b[0m\x1b[93mg'
            '\x1b[0m\x1b[93md\x1b[0m \x1b[93ma\x1b[0m\x1b[93mi\x1b[0m'
            '\x1b[93mu\x1b[0m\x1b[93me\x1b[0m\x1b[93mo\x1b[0m\n')


@unittest.skipUnless(os.name == 'nt', 'requires Windows console')
class WindowsTerminalTestCase(UITestCase):

    """MS Windows terminal tests."""

    @classmethod
    def setUpClass(cls):
        if os.name != 'nt':
            raise unittest.SkipTest('requires Windows console')
        if not win32api:
            raise unittest.SkipTest('requires Windows package pywin32')
        if not win32clipboard:
            raise unittest.SkipTest('requires Windows package win32clipboard')
        if not pywinauto:
            raise unittest.SkipTest('requires Windows package pywinauto')
        try:
            # pywinauto 0.5.0
            cls._app = pywinauto.Application()
        except AttributeError as e1:
            try:
                cls._app = pywinauto.application.Application()
            except AttributeError as e2:
                raise unittest.SkipTest('pywinauto Application failed: {}\n{}'
                                        .format(e1, e2))
        super().setUpClass()

    @classmethod
    def setUpProcess(cls, command):
        si = subprocess.STARTUPINFO()
        si.dwFlags = subprocess.STARTF_USESTDHANDLES
        cls._process = subprocess.Popen(
            command, creationflags=subprocess.CREATE_NEW_CONSOLE)

        cls._app.connect_(process=cls._process.pid)

        # set truetype font (Lucida Console, hopefully)
        try:
            window = cls._app.window_()
        except Exception as e:
            cls.tearDownProcess()
            raise unittest.SkipTest(
                'Windows package pywinauto could not locate window: {!r}'
                .format(e))

        try:
            window.TypeKeys('% {UP}{ENTER}%L{HOME}L{ENTER}', with_spaces=True)
        except Exception as e:
            cls.tearDownProcess()
            raise unittest.SkipTest(
                'Windows package pywinauto could not use window TypeKeys: {!r}'
                .format(e))

    @classmethod
    def tearDownProcess(cls):
        cls._process.kill()

    def setUp(self):
        super().setUp()
        self.setclip('')

    def waitForWindow(self):
        while not self._app.window_().IsEnabled():
            time.sleep(0.01)

    def getstdouterr(self):
        sentinel = '~~~~SENTINEL~~~~cedcfc9f-7eed-44e2-a176-d8c73136c185'
        # select all and copy to clipboard
        self._app.window_().SetFocus()
        self.waitForWindow()
        self._app.window_().TypeKeys(
            '% {UP}{UP}{UP}{RIGHT}{DOWN}{DOWN}{DOWN}{ENTER}{ENTER}',
            with_spaces=True)

        while True:
            data = self.getclip()
            if data != sentinel:
                return data
            time.sleep(0.01)

    def setclip(self, text):
        win32clipboard.OpenClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_UNICODETEXT, text)
        win32clipboard.CloseClipboard()

    def getclip(self):
        win32clipboard.OpenClipboard()
        data = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
        win32clipboard.CloseClipboard()
        data = data.split('\x00')[0]
        data = data.replace('\r\n', '\n')
        return data

    def sendstdin(self, text):
        self.setclip(text.replace('\n', '\r\n'))
        self._app.window_().SetFocus()
        self.waitForWindow()
        self._app.window_().TypeKeys(
            '% {UP}{UP}{UP}{RIGHT}{DOWN}{DOWN}{ENTER}',
            with_spaces=True)


class TestWindowsTerminalUnicode(WindowsTerminalTestCase):

    """MS Windows terminal unicode tests."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        fn = inspect.getfile(inspect.currentframe())
        cls.setUpProcess(['python', 'pwb.py', fn,
                          '--run-as-slave-interpreter'])

        _manager.connect()
        cls.pywikibot = _manager.pywikibot()

    @classmethod
    def tearDownClass(cls):
        del cls.pywikibot
        cls.tearDownProcess()

    def setUp(self):
        super().setUp()

        self.pywikibot.set_config('colorized_output', True)
        self.pywikibot.set_config('transliterate', False)
        self.pywikibot.set_config('console_encoding', 'utf-8')
        self.pywikibot.set_ui('transliteration_target', None)
        self.pywikibot.set_ui('encoding', 'utf-8')

        self.pywikibot.cls()

    def testOutputUnicodeText_no_transliterate(self):
        self.pywikibot.output('Заглавная_страница')
        self.assertEqual(self.getstdouterr(), 'Заглавная_страница\n')

    def testOutputUnicodeText_transliterate(self):
        self.pywikibot.set_config('transliterate', True)
        self.pywikibot.set_ui('transliteration_target', 'latin-1')
        self.pywikibot.output('Заглавная_страница')
        self.assertEqual(self.getstdouterr(), 'Zaglavnaya_stranica\n')

    def testInputUnicodeText(self):
        self.pywikibot.set_config('transliterate', True)

        self.pywikibot.request_input('Википедию? ')
        self.assertEqual(self.getstdouterr(), 'Википедию?')
        self.sendstdin('Заглавная_страница\n')
        returned = self.pywikibot.get_input()

        self.assertEqual(returned, 'Заглавная_страница')


class TestWindowsTerminalUnicodeArguments(WindowsTerminalTestCase):

    """MS Windows terminal unicode argument tests."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.setUpProcess(['cmd', '/k', 'echo off'])

    @classmethod
    def tearDownClass(cls):
        cls.tearDownProcess()

    def testOutputUnicodeText_no_transliterate(self):
        self.sendstdin(
            'python -c \"'
            'import subprocess, pywikibot; '
            "subprocess.run('cls', shell=True); "
            "pywikibot.output('\\n'.join(pywikibot.handle_args()))\" "
            'Alpha Bετα Гамма دلتا\n')
        lines = []

        for i in range(3):
            lines = self.getstdouterr().split('\n')
            if len(lines) >= 4 and 'Alpha' not in lines:
                # if len(lines) < 4, we assume not all lines had been output
                # yet, and retry. We check at least one of the lines contains
                # "Alpha" to prevent using older clipboard content. We limit
                # the number of retries to 3 so that the test will finish even
                # if neither of these requirements are met.
                break
            time.sleep(1)

        # empty line is the new command line
        self.assertEqual(lines, ['Alpha', 'Bετα', 'Гамма', 'دلتا', ''])


# TODO: add tests for background colors.
class FakeUITest(TestCase):

    """Test case to allow doing uncolorized general UI tests."""

    net = False

    expected = 'Hello world you! ***'
    expect_color = False
    ui_class = terminal_interface_base.UI

    def setUp(self):
        """Create dummy instances for the test and patch encounter_color."""
        super().setUp()
        self.stream = io.StringIO()
        self.ui_obj = self.ui_class()
        self._orig_encounter_color = self.ui_obj.encounter_color
        self.ui_obj.encounter_color = self._encounter_color
        self._index = 0

    def tearDown(self):
        """Unpatch the encounter_color method."""
        self.ui_obj.encounter_color = self._orig_encounter_color
        super().tearDown()
        self.assertEqual(self._index,
                         len(self._colors) if self.expect_color else 0)

    def _getvalue(self):
        """Get the value of the stream."""
        return self.stream.getvalue()

    def _encounter_color(self, color, target_stream):
        """Patched encounter_color method."""
        raise AssertionError('This method should not be invoked')

    def test_no_color(self):
        """Test a string without any colors."""
        self._colors = ()
        self.ui_obj._print('Hello world you!', self.stream)
        self.assertEqual(self._getvalue(), 'Hello world you!')

    def test_one_color(self):
        """Test a string using one color."""
        self._colors = (('red', 6), ('default', 10))
        self.ui_obj._print('Hello \03{red}world you!', self.stream)
        self.assertEqual(self._getvalue(), self.expected)

    def test_flat_color(self):
        """Test using colors with defaulting in between."""
        self._colors = (('red', 6), ('default', 6), ('yellow', 3),
                        ('default', 1))
        self.ui_obj._print('Hello \03{red}world \03{default}you\03{yellow}!',
                           self.stream)
        self.assertEqual(self._getvalue(), self.expected)

    def test_stack_with_pop_color(self):
        """Test using stacked colors and just popping the latest color."""
        self._colors = (('red', 6), ('yellow', 6), ('red', 3), ('default', 1))
        self.ui_obj._print('Hello \03{red}world \03{yellow}you\03{previous}!',
                           self.stream)
        self.assertEqual(self._getvalue(), self.expected)

    def test_stack_implicit_color(self):
        """Test using stacked colors without popping any."""
        self._colors = (('red', 6), ('yellow', 6), ('default', 4))
        self.ui_obj._print('Hello \03{red}world \03{yellow}you!', self.stream)
        self.assertEqual(self._getvalue(), self.expected)

    def test_one_color_newline(self):
        """Test with trailing new line and one color."""
        self._colors = (('red', 6), ('default', 11))
        self.ui_obj._print('Hello \03{red}world you!\n', self.stream)
        self.assertEqual(self._getvalue(), self.expected + '\n')


class FakeUIColorizedTestBase(TestCase):

    """Base class for test cases requiring that colorized output is active."""

    expect_color = True

    def setUp(self):
        """Force colorized_output to True."""
        super().setUp()
        self._old_config = pywikibot.config2.colorized_output
        pywikibot.config2.colorized_output = True

    def tearDown(self):
        """Undo colorized_output configuration."""
        pywikibot.config2.colorized_output = self._old_config
        super().tearDown()


class FakeUnixTest(FakeUIColorizedTestBase, FakeUITest):

    """Test case to allow doing colorized Unix tests in any environment."""

    net = False

    expected = 'Hello world you!'
    ui_class = terminal_interface_unix.UnixUI

    def _encounter_color(self, color, target_stream):
        """Verify that the written data, color and stream are correct."""
        self.assertIs(target_stream, self.stream)
        expected_color = self._colors[self._index][0]
        self._index += 1
        self.assertEqual(color, expected_color)
        self.assertLength(self.stream.getvalue(),
                          sum(e[1] for e in self._colors[:self._index]))


class FakeWin32Test(FakeUIColorizedTestBase, FakeUITest):

    """
    Test case to allow doing colorized Win32 tests in any environment.

    This only patches the ctypes import in the terminal_interface_win32
    module. As the Win32CtypesUI is using the std-streams from another
    import these will be unpatched.
    """

    net = False

    expected = 'Hello world you!'
    ui_class = terminal_interface_win32.Win32UI

    def setUp(self):
        """Patch the ctypes import and initialize a stream and UI instance."""
        super().setUp()
        self._orig_ctypes = terminal_interface_win32.ctypes
        ctypes = FakeModule.create_dotted('ctypes.windll.kernel32')
        ctypes.windll.kernel32.SetConsoleTextAttribute = self._handle_setattr
        terminal_interface_win32.ctypes = ctypes
        self.stream._hConsole = object()

    def tearDown(self):
        """Unpatch the ctypes import and check that all colors were used."""
        terminal_interface_win32.ctypes = self._orig_ctypes
        super().tearDown()

    def _encounter_color(self, color, target_stream):
        """Call the original method."""
        self._orig_encounter_color(color, target_stream)

    def _handle_setattr(self, handle, attribute):
        """Dummy method to handle SetConsoleTextAttribute."""
        self.assertIs(handle, self.stream._hConsole)
        color = self._colors[self._index][0]
        self._index += 1
        color = terminal_interface_win32.windowsColors[color]
        self.assertEqual(attribute, color)
        self.assertLength(self.stream.getvalue(),
                          sum(e[1] for e in self._colors[:self._index]))


class FakeWin32UncolorizedTest(FakeWin32Test):

    """Test case to allow doing uncolorized Win32 tests in any environment."""

    net = False

    expected = 'Hello world you! ***'
    expect_color = False

    def setUp(self):
        """Change the local stream's console to None to disable colors."""
        super().setUp()
        self.stream._hConsole = None


if __name__ == '__main__':  # pragma: no cover
    try:
        with suppress(SystemExit):
            unittest.main()
    finally:
        unpatch()
