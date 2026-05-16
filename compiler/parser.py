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
            return self._parse_let()

        # if 语句
        if t.kind == TokenKind.IF:
            return self._parse_if()

        # while 语句
        if t.kind == TokenKind.WHILE:
            return self._parse_while()

        # 标识符开头的语句：赋值 或 表达式语句
        if t.kind == TokenKind.IDENT:
            return self._parse_ident_stmt()

        # 其他表达式语句
        expr = self.parse_expression()
        stmt = ExpressionStatement(expr)
        self.match(TokenKind.SEMI)
        return stmt

    def _parse_let(self):
        self.advance()  # 吞 let
        mut = self.match(TokenKind.IDENT) and self.tokens[self.pos - 1].value == "mut"
        if mut:
            name = self.expect(TokenKind.IDENT).value
        else:
            name = self.tokens[self.pos - 1].value
        self.expect(TokenKind.EQ)
        init = self.parse_expression()
        stmt = VariableDeclaration(name, mut, init)
        self.match(TokenKind.SEMI)
        return stmt

    def _parse_if(self):
        self.advance()  # 吞 if
        condition = self.parse_expression()
        then_block = self._parse_block()
        else_block = None
        if self.peek().kind == TokenKind.ELSE:
            self.advance()
            # else 后可接 if（else if）或 {
            if self.peek().kind == TokenKind.IF:
                else_block = Block([self._parse_if()])
            else:
                else_block = self._parse_block()
        self.match(TokenKind.SEMI)  # if 后可选的 ;
        return If(condition, then_block, else_block)

    def _parse_while(self):
        self.advance()  # 吞 while
        condition = self.parse_expression()
        body = self._parse_block()
        self.match(TokenKind.SEMI)
        return While(condition, body)

    def _parse_block(self):
        self.expect(TokenKind.LBRACE)
        stmts = []
        while self.peek().kind not in (TokenKind.RBRACE, TokenKind.EOF):
            stmts.append(self.parse_statement())
        self.expect(TokenKind.RBRACE)
        return Block(stmts)

    def _parse_ident_stmt(self):
        t = self.peek()
        name = t.value
        if self.pos + 1 < len(self.tokens) and self.tokens[self.pos + 1].kind == TokenKind.EQ:
            self.advance()  # 吞 ident
            self.advance()  # 吞 =
            expr = self.parse_expression()
            stmt = Assignment(name, expr)
        else:
            expr = self.parse_expression()
            stmt = ExpressionStatement(expr)
        self.match(TokenKind.SEMI)
        return stmt

    # ========== 表达式（含比较级） ==========

    def parse_expression(self):
        return self.parse_comparison()

    def parse_comparison(self):
        left = self.parse_additive()
        cmp_ops = {TokenKind.GT, TokenKind.LT, TokenKind.GE, TokenKind.LE, TokenKind.EQEQ, TokenKind.NE}
        while self.peek().kind in cmp_ops:
            op = self.advance().value
            right = self.parse_additive()
            left = BinaryOp(left, op, right)
        return left

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
