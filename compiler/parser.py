"""递归下降解析器 —— Token 流 → AST。"""

from compiler.ast import *
from compiler.lexer import Token, TokenKind


class ParseError(Exception):
    pass


class Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.pos = 0

    def peek(self) -> Token:
        return self.tokens[self.pos]

    def advance(self) -> Token:
        t = self.tokens[self.pos]
        self.pos += 1
        return t

    def expect(self, kind: TokenKind) -> Token:
        t = self.peek()
        if t.kind != kind:
            raise ParseError(f"Expected {kind}, got {t}")
        return self.advance()

    def match(self, kind: TokenKind) -> bool:
        if self.peek().kind == kind:
            self.advance()
            return True
        return False

    # ========== 程序入口 ==========

    def parse_program(self) -> Program:
        stmts = []
        while self.peek().kind != TokenKind.EOF:
            stmts.append(self.parse_statement())
        return Program(stmts)

    # ========== 语句 ==========

    def parse_statement(self):
        t = self.peek()

        # let 声明
        if t.kind == TokenKind.LET:
            self.advance()  # 吞 let
            mut = self.match(TokenKind.IDENT) and self.tokens[self.pos - 1].value == "mut"
            if mut:
                name = self.expect(TokenKind.IDENT).value
            else:
                # 已经吞了 IDENT，就是 name
                name = self.tokens[self.pos - 1].value
            self.expect(TokenKind.EQ)
            init = self.parse_expression()
            stmt = VariableDeclaration(name, mut, init)

        # 标识符开头的语句：可能是赋值 或 表达式语句（函数调用）
        elif t.kind == TokenKind.IDENT:
            # 预读：若后面是 = 则为赋值
            name = t.value
            if self.pos + 1 < len(self.tokens) and self.tokens[self.pos + 1].kind == TokenKind.EQ:
                self.advance()  # 吞 ident
                self.advance()  # 吞 =
                expr = self.parse_expression()
                stmt = Assignment(name, expr)
            else:
                expr = self.parse_expression()
                stmt = ExpressionStatement(expr)
        else:
            expr = self.parse_expression()
            stmt = ExpressionStatement(expr)

        # 语句结束符
        self.match(TokenKind.SEMI)
        return stmt

    # ========== 表达式 ==========

    def parse_expression(self):
        return self.parse_additive()

    def parse_additive(self):
        left = self.parse_multiplicative()
        while self.peek().kind in (TokenKind.PLUS, TokenKind.MINUS):
            op = self.advance().value
            right = self.parse_multiplicative()
            left = BinaryOp(left, op, right)
        return left

    def parse_multiplicative(self):
        left = self.parse_primary()
        while self.peek().kind in (TokenKind.STAR, TokenKind.SLASH, TokenKind.PERCENT):
            op = self.advance().value
            right = self.parse_primary()
            left = BinaryOp(left, op, right)
        return left

    def parse_primary(self):
        t = self.peek()

        if t.kind == TokenKind.INTEGER:
            self.advance()
            return IntegerLiteral(t.value)

        if t.kind == TokenKind.IDENT:
            name = self.advance().value
            if self.peek().kind == TokenKind.LPAREN:
                self.advance()  # 吞 (
                args = []
                if self.peek().kind != TokenKind.RPAREN:
                    args.append(self.parse_expression())
                    while self.peek().kind != TokenKind.RPAREN:
                        raise ParseError("Only one arg supported for now")
                self.expect(TokenKind.RPAREN)
                return FunctionCall(name, args)
            return Identifier(name)

        if t.kind == TokenKind.LPAREN:
            self.advance()
            expr = self.parse_expression()
            self.expect(TokenKind.RPAREN)
            return expr

        raise ParseError(f"Unexpected token: {t}")


def parse(tokens: list[Token]) -> Program:
    return Parser(tokens).parse_program()
