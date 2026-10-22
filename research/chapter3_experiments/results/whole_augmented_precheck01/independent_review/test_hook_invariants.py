"""AST-only optional-hook review. No production imports or model construction."""
import ast
from copy import deepcopy
from pathlib import Path
import unittest

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
OLD=ROOT/'results/deadline_execution01/source_snapshot/research/chapter3_experiments/formal_milp.py'
NEW=ROOT/'formal_milp.py'


def dump(node):return ast.dump(node,include_attributes=False)


def tree(path):return ast.parse(path.read_text(encoding='utf-8-sig'))


def functions(value):return {n.name:n for n in value.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}


def remove_optional(fn,name,default):
    indices=[i for i,arg in enumerate(fn.args.kwonlyargs) if arg.arg==name]
    if len(indices)!=1:raise AssertionError(f'Expected one {name} keyword-only hook')
    index=indices[0]
    if dump(fn.args.kw_defaults[index])!=dump(ast.parse(default,mode='eval').body):
        raise AssertionError(f'Unexpected {name} default')
    fn.args.kwonlyargs.pop(index);fn.args.kw_defaults.pop(index)


class HookInvariantTests(unittest.TestCase):
    def test_only_two_expected_functions_change(self):
        old,new=tree(OLD),tree(NEW)
        def keep(t):return [dump(n) for n in t.body if getattr(n,'name',None) not in (
            'solve_formal_diagnostic','execute_formal_milp')]
        self.assertEqual(keep(old),keep(new))

    def test_recorder_hook_restores_entire_old_outer_loop(self):
        old=functions(tree(OLD))['solve_formal_diagnostic']
        new=deepcopy(functions(tree(NEW))['solve_formal_diagnostic'])
        remove_optional(new,'recorder_factory','Recorder')
        class Restore(ast.NodeTransformer):
            def visit_Name(self,node):
                return ast.copy_location(ast.Name(id='Recorder',ctx=node.ctx),node) if node.id=='recorder_factory' else node
        new=Restore().visit(new)
        self.assertEqual(dump(old),dump(new))

    def test_solver_hook_restores_entire_old_formal_entry(self):
        old=functions(tree(OLD))['execute_formal_milp']
        new=deepcopy(functions(tree(NEW))['execute_formal_milp'])
        remove_optional(new,'diagnostic_solver','None')
        assignments=[n for n in new.body if isinstance(n,ast.Assign)
            and len(n.targets)==1 and isinstance(n.targets[0],ast.Name) and n.targets[0].id=='selected_solver']
        self.assertEqual(len(assignments),1)
        expected=ast.parse('solve_formal_diagnostic if diagnostic_solver is None else diagnostic_solver',mode='eval').body
        self.assertEqual(dump(assignments[0].value),dump(expected))
        new.body.remove(assignments[0])
        class Restore(ast.NodeTransformer):
            def visit_Name(self,node):
                return ast.copy_location(ast.Name(id='solve_formal_diagnostic',ctx=node.ctx),node) if node.id=='selected_solver' else node
        new=Restore().visit(new)
        self.assertEqual(dump(old),dump(new))


if __name__=='__main__':unittest.main(verbosity=2)
