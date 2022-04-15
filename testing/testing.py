import os


class CompilerTest:
    def __init__(self):
        self.working_dir = './temp/'

    def setup(self):
        pass

    def run(self) -> bool:
        return True

    def cleanup(self):
        import os
        import glob
        for f in glob.glob('./temp/*.*'):
            os.remove(f)
        os.removedirs('./temp')


class BlankFileTest(CompilerTest):
    def setup(self):
        os.makedirs('./temp')
        main = "fn main(): int {}"
        with open(self.working_dir + 'main.sat', 'w') as f:
            f.write(main)

    def test(self):
        from main import compile_package, PackageType
        try:
            compile_package('main', self.working_dir, package_type=PackageType.PROGRAM)
        except Exception:
            return False
        import os.path
        if not os.path.isfile(self.working_dir + 'main.ll'):
            return False
        return True


class MultipleFilesTest(CompilerTest):
    def setup(self):
        os.makedirs('./temp')
        main = """
        fn main(): int {
            return other_func(4);
        }
        """
        with open(self.working_dir + 'main.sat', 'w') as f:
            f.write(main)
        other = """
        fn other_func(x: int): int {
            return x + 1;
        }
        """
        with open(self.working_dir + 'other.sat', 'w') as f:
            f.write(other)

    def test(self):
        from main import compile_package, PackageType
        try:
            compile_package('main', self.working_dir, package_type=PackageType.PROGRAM)
        except Exception:
            return False
        import os.path
        if not os.path.isfile(self.working_dir + 'main.ll'):
            return False
        return True


def perform_test(test_class) -> bool:
    test = test_class()
    test.setup()
    result = test.test()
    test.cleanup()
    if result:
        print(f'Passed {test_class.__name__}!')
    else:
        print(f'Failed {test_class.__name__}!')
    return result


def perform_tests() -> bool:
    p = True
    p = p and perform_test(BlankFileTest)
    p = p and perform_test(MultipleFilesTest)
    return p


perform_tests()
