"""运行清单核验入口：总回归加连读专项，任一失败即以非零状态退出。"""
import sys
import unittest


def load_suite(name: str) -> unittest.TestSuite:
    if name == 'check_project':
        return unittest.defaultTestLoader.discover('tests', top_level_dir='.')
    return unittest.defaultTestLoader.loadTestsFromName(name)


def main() -> int:
    runner = unittest.TextTestRunner(verbosity=2)
    total = 0
    success = True
    for name in ('check_project', 'check_liandu_seed'):
        result = runner.run(load_suite(name))
        total += result.testsRun
        success = success and result.wasSuccessful()
    print(f'VERIFY SUMMARY tests={total} result={"PASS" if success else "FAIL"}')
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
