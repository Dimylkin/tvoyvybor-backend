"""Small bounded Python teaching interpreter. Never executes host Python code.

Supported: function, assignments, for/if, return, numeric operators, lists,
comprehensions, sum/len, and append. No imports, arbitrary calls or attributes.
"""

import ast
import operator


class InvalidProgram(ValueError):
    pass


class Returned(Exception):
    def __init__(self, value):
        self.value = value


class Interpreter:
    def __init__(self):
        self.budget = 3000

    def evaluate(self, node, env):
        self.budget -= 1
        if self.budget < 0:
            raise InvalidProgram("Слишком много операций")
        match node:
            case ast.Constant(value=value) if value is None or type(value) in (
                int,
                float,
                bool,
            ):
                if isinstance(value, (int, float)) and abs(value) > 1e6:
                    raise InvalidProgram("Слишком большое число")
                return value
            case ast.Name(id=name):
                if name not in env:
                    raise InvalidProgram(f"Неизвестное имя: {name}")
                return env[name]
            case ast.List(elts=items):
                return [self.evaluate(x, env) for x in items]
            case ast.BinOp(left=left, op=op, right=right):
                operations = {
                    ast.Add: operator.add,
                    ast.Sub: operator.sub,
                    ast.Mult: operator.mul,
                    ast.Div: operator.truediv,
                }
                if type(op) not in operations:
                    raise InvalidProgram("Доступны +, -, *, /")
                a, b = self.evaluate(left, env), self.evaluate(right, env)
                if type(a) not in (int, float) or type(b) not in (int, float):
                    raise InvalidProgram("Арифметика работает с числами")
                result = operations[type(op)](a, b)
                if abs(result) > 1e12:
                    raise InvalidProgram("Слишком большой результат")
                return result
            case ast.Compare(left=left, ops=ops, comparators=values):
                operations = {
                    ast.Is: operator.is_,
                    ast.IsNot: operator.is_not,
                    ast.Eq: operator.eq,
                    ast.NotEq: operator.ne,
                    ast.Gt: operator.gt,
                    ast.Lt: operator.lt,
                    ast.GtE: operator.ge,
                    ast.LtE: operator.le,
                }
                a = self.evaluate(left, env)
                for op, value in zip(ops, values):
                    if type(op) not in operations:
                        raise InvalidProgram("Недоступное сравнение")
                    b = self.evaluate(value, env)
                    if not operations[type(op)](a, b):
                        return False
                    a = b
                return True
            case ast.UnaryOp(op=ast.Not(), operand=value):
                return not self.evaluate(value, env)
            case ast.UnaryOp(op=ast.USub(), operand=value):
                return -self.evaluate(value, env)
            case ast.IfExp(test=test, body=body, orelse=other):
                return self.evaluate(body if self.evaluate(test, env) else other, env)
            case ast.Call(func=ast.Name(id=name), args=[value], keywords=[]) if (
                name in ("sum", "len")
            ):
                value = self.evaluate(value, env)
                if not isinstance(value, list):
                    raise InvalidProgram("sum/len ожидает список")
                return sum(value) if name == "sum" else len(value)
            case ast.ListComp(
                elt=elt,
                generators=[
                    ast.comprehension(
                        target=ast.Name(id=name), iter=items, ifs=ifs, is_async=0
                    )
                ],
            ):
                values = self.evaluate(items, env)
                if not isinstance(values, list):
                    raise InvalidProgram("Ожидается список")
                return [
                    self.evaluate(elt, {**env, name: item})
                    for item in values
                    if all(self.evaluate(test, {**env, name: item}) for test in ifs)
                ]
            case _:
                raise InvalidProgram("Эта конструкция не поддерживается учебным Python")

    def block(self, statements, env):
        for node in statements:
            self.budget -= 1
            if self.budget < 0:
                raise InvalidProgram("Слишком много операций")
            match node:
                case ast.Assign(targets=[ast.Name(id=name)], value=value):
                    env[name] = self.evaluate(value, env)
                case ast.AugAssign(target=ast.Name(id=name), op=op, value=value):
                    env[name] = self.evaluate(
                        ast.BinOp(left=ast.Name(id=name), op=op, right=value), env
                    )
                case ast.Return(value=value):
                    raise Returned(self.evaluate(value, env) if value else None)
                case ast.If(test=test, body=body, orelse=other):
                    self.block(body if self.evaluate(test, env) else other, env)
                case ast.For(
                    target=ast.Name(id=name), iter=items, body=body, orelse=[]
                ):
                    values = self.evaluate(items, env)
                    if not isinstance(values, list):
                        raise InvalidProgram("Цикл ожидает список")
                    for item in values[:100]:
                        env[name] = item
                        self.block(body, env)
                case ast.Expr(
                    value=ast.Call(
                        func=ast.Attribute(value=ast.Name(id=name), attr="append"),
                        args=[value],
                        keywords=[],
                    )
                ):
                    target = env.get(name)
                    if not isinstance(target, list) or len(target) >= 100:
                        raise InvalidProgram("append ожидает короткий список")
                    target.append(self.evaluate(value, env))
                case _:
                    raise InvalidProgram("Используйте присваивание, for, if и return")

    def run(self, code, grades):
        tree = ast.parse(code)
        if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef):
            raise InvalidProgram("Ожидается одна функция calculate_average(grades)")
        fn = tree.body[0]
        if (
            fn.name != "calculate_average"
            or len(fn.args.args) != 1
            or fn.decorator_list
            or fn.args.defaults
            or fn.args.vararg
            or fn.args.kwarg
            or fn.args.kwonlyargs
            or fn.args.posonlyargs
        ):
            raise InvalidProgram("Сохраните сигнатуру calculate_average(grades)")
        try:
            self.block(fn.body, {fn.args.args[0].arg: grades})
        except Returned as result:
            return result.value
        return None


def check_code(code):
    cases = [
        ([4, 5, 3], 4),
        ([5, None, 3], 4),
        ([], 0),
        ([None, None], 0),
        ([0, 4, None], 2),
        ([1, 2], 1.5),
    ]
    results = []
    for grades, expected in cases:
        try:
            actual = Interpreter().run(code, list(grades))
            passed = type(actual) in (int, float) and abs(actual - expected) < 1e-8
            detail = f"Получено {actual}; ожидается {expected}"
        except (
            InvalidProgram,
            SyntaxError,
            TypeError,
            ZeroDivisionError,
            OverflowError,
            RecursionError,
        ) as exc:
            passed, detail = False, str(exc)
        results.append({"input": grades, "passed": passed, "detail": detail[:250]})
    return results
