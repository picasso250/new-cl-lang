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

    def span(self, node, start: Token):
        node.span = (start.pos, self.tokens[self.pos - 1].pos)
        return node

    # ========== 程序入口 ==========

    def parse_program(self) -> Program:
        stmts = []
        while self.peek().kind != TokenKind.EOF:
            stmts.append(self.parse_statement())
        return Program(stmts)

    # ========== 语句 ==========

    def parse_statement(self):
        t = self.peek()

        if t.kind == TokenKind.LET:
            return self._parse_let()
        if t.kind == TokenKind.IF:
            expr = self.parse_expression()
            stmt = ExpressionStatement(expr)
            self.match(TokenKind.SEMI)
            return stmt
        if t.kind == TokenKind.FUN and self._is_function_declaration_start():
            return self._parse_function()
        if t.kind == TokenKind.RETURN:
            return self._parse_return()
        if t.kind == TokenKind.STRUCT:
            return self._parse_struct()
        if t.kind == TokenKind.ENUM:
            return self._parse_enum()
        if t.kind == TokenKind.SWITCH:
            return self._parse_switch()
        if t.kind == TokenKind.FOR:
            return self._parse_for()
        if t.kind == TokenKind.TRY:
            return self._parse_try()
        if t.kind == TokenKind.THROW:
            return self._parse_throw()
        if t.kind == TokenKind.DEFER:
            return self._parse_defer()
        if t.kind == TokenKind.BREAK:
            start = self.advance()
            self.match(TokenKind.SEMI)
            return self.span(Break(), start)
        if t.kind == TokenKind.IDENT:
            return self._parse_ident_stmt()

        expr = self.parse_expression()
        stmt = ExpressionStatement(expr)
        self.match(TokenKind.SEMI)
        return stmt

    def _is_function_declaration_start(self):
        if self.peek().kind != TokenKind.FUN:
            return False
        if self.pos + 1 >= len(self.tokens):
            return False
        nxt = self.tokens[self.pos + 1]
        if nxt.kind == TokenKind.IDENT:
            return True
        if nxt.kind == TokenKind.LPAREN and self.pos + 4 < len(self.tokens):
            return (self.tokens[self.pos + 2].kind == TokenKind.IDENT
                    and self.tokens[self.pos + 3].kind == TokenKind.STAR
                    and self.tokens[self.pos + 4].kind == TokenKind.IDENT)
        return False

    def _parse_let(self):
        start = self.advance()
        name = self.expect(TokenKind.IDENT).value
        annotation = None
        if self.peek().kind == TokenKind.COLON:
            self.advance()
            annotation = self._parse_type()
        self.expect(TokenKind.EQ)
        init = self.parse_expression()
        stmt = self.span(VariableDeclaration(name, init, annotation), start)
        self.match(TokenKind.SEMI)
        return stmt

    def _parse_type(self) -> str:
        if self.peek().kind == TokenKind.LPAREN:
            self.advance()
            params = []
            if self.peek().kind != TokenKind.RPAREN:
                params.append(self._parse_type())
                while self.peek().kind == TokenKind.COMMA:
                    self.advance()
                    params.append(self._parse_type())
            self.expect(TokenKind.RPAREN)
            self.expect(TokenKind.ARROW)
            ret = self._parse_type()
            return f"fn({','.join(params)})->{ret}"
        if self.peek().kind == TokenKind.STAR:
            self.advance()
            return "*" + self._parse_type()
        if self.peek().kind == TokenKind.LBRACKET:
            self.advance()
            length = None
            if self.peek().kind != TokenKind.RBRACKET:
                length = self.expect(TokenKind.INTEGER).value
            self.expect(TokenKind.RBRACKET)
            elem = self._parse_type()
            return f"[]{elem}" if length is None else f"[{length}]{elem}"
        return self.expect(TokenKind.IDENT).value

    def _parse_function(self):
        self.advance()  # 吃 fun
        # 方法接收者？
        receiver_name = None
        receiver_type = None
        if self.peek().kind == TokenKind.LPAREN:
            self.advance()
            rname = self.expect(TokenKind.IDENT).value
            self.expect(TokenKind.STAR)
            rtype = self.expect(TokenKind.IDENT).value
            self.expect(TokenKind.RPAREN)
            receiver_name = rname
            receiver_type = "*" + rtype
        name = self.expect(TokenKind.IDENT).value
        self.expect(TokenKind.LPAREN)
        params = []
        if self.peek().kind != TokenKind.RPAREN:
            pname = self.expect(TokenKind.IDENT).value
            self.expect(TokenKind.COLON)
            ptype = self._parse_type()
            params.append((pname, ptype))
            while self.peek().kind == TokenKind.COMMA:
                self.advance()
                pname = self.expect(TokenKind.IDENT).value
                self.expect(TokenKind.COLON)
                ptype = self._parse_type()
                params.append((pname, ptype))
        self.expect(TokenKind.RPAREN)
        return_type = None
        return_type_explicit = False
        if self.peek().kind == TokenKind.COLON:
            self.advance()
            return_type = self._parse_type()
            return_type_explicit = True
        body = self._parse_block()
        self.match(TokenKind.SEMI)
        return FunctionDeclaration(name, params, return_type, body,
                                   receiver_name, receiver_type, return_type_explicit)

    def _parse_function_expr(self, start):
        self.expect(TokenKind.LPAREN)
        params = []
        if self.peek().kind != TokenKind.RPAREN:
            pname = self.expect(TokenKind.IDENT).value
            self.expect(TokenKind.COLON)
            ptype = self._parse_type()
            params.append((pname, ptype))
            while self.peek().kind == TokenKind.COMMA:
                self.advance()
                pname = self.expect(TokenKind.IDENT).value
                self.expect(TokenKind.COLON)
                ptype = self._parse_type()
                params.append((pname, ptype))
        self.expect(TokenKind.RPAREN)
        return_type = None
        return_type_explicit = False
        if self.peek().kind == TokenKind.COLON:
            self.advance()
            return_type = self._parse_type()
            return_type_explicit = True
        body = self._parse_block()
        return self.span(FunctionExpr(params, return_type, body, return_type_explicit), start)

    def _parse_return(self):
        start = self.advance()
        expr = None
        if self.peek().kind != TokenKind.SEMI and self.peek().kind != TokenKind.RBRACE:
            expr = self.parse_expression()
        stmt = self.span(Return(expr), start)
        self.match(TokenKind.SEMI)
        return stmt

    def _parse_try(self):
        self.advance()
        body = self._parse_block()
        self.expect(TokenKind.CATCH)
        error_name = self.expect(TokenKind.IDENT).value
        catch_body = self._parse_block()
        return TryCatch(body, error_name, catch_body)

    def _parse_throw(self):
        start = self.advance()
        expr = self.parse_expression()
        self.match(TokenKind.SEMI)
        return self.span(Throw(expr), start)

    def _parse_defer(self):
        start = self.advance()
        body = self._parse_block()
        return self.span(Defer(body), start)

    def _parse_for(self):
        self.advance()  # 吞 for
        if self.peek().kind != TokenKind.IDENT:
            condition = self.parse_expression()
            body = self._parse_block()
            self.match(TokenKind.SEMI)
            return While(condition, body)

        save = self.pos
        idx = self.expect(TokenKind.IDENT).value
        if self.peek().kind == TokenKind.COMMA:
            # for i, v in iterable { }
            self.advance()
            val = self.expect(TokenKind.IDENT).value
            self.expect(TokenKind.IN)
            iterable = self.parse_expression()
            body = self._parse_block()
            return ForIn(idx, val, iterable, body)
        if self.peek().kind == TokenKind.IN:
            # for i in start..end { }
            self.advance()
            start = self.parse_expression()
            self.expect(TokenKind.DOTDOT)
            end = self.parse_expression()
            body = self._parse_block()
            return ForIn(idx, None, None, body, start=start, end=end)

        self.pos = save
        condition = self.parse_expression()
        body = self._parse_block()
        self.match(TokenKind.SEMI)
        return While(condition, body)

    def _parse_struct(self):
        self.advance()  # 吞 struct
        name = self.expect(TokenKind.IDENT).value
        self.expect(TokenKind.LBRACE)
        fields = []
        if self.peek().kind != TokenKind.RBRACE:
            fname = self.expect(TokenKind.IDENT).value
            self.expect(TokenKind.COLON)
            ftype = self._parse_type()
            fields.append((fname, ftype))
            while self.peek().kind == TokenKind.COMMA:
                self.advance()
                fname = self.expect(TokenKind.IDENT).value
                self.expect(TokenKind.COLON)
                ftype = self._parse_type()
                fields.append((fname, ftype))
        self.expect(TokenKind.RBRACE)
        stmt = StructDecl(name, fields)
        self.match(TokenKind.SEMI)
        return stmt

    def _parse_enum(self):
        self.advance()  # 吞 enum
        name = self.expect(TokenKind.IDENT).value
        self.expect(TokenKind.LBRACE)
        variants = []
        if self.peek().kind != TokenKind.RBRACE:
            variants.append(self.expect(TokenKind.IDENT).value)
            while self.peek().kind == TokenKind.COMMA:
                self.advance()
                variants.append(self.expect(TokenKind.IDENT).value)
        self.expect(TokenKind.RBRACE)
        stmt = EnumDecl(name, variants)
        self.match(TokenKind.SEMI)
        return stmt

    def _parse_switch(self):
        self.advance()  # 吞 switch
        scrutinee = self.parse_expression()
        self.expect(TokenKind.LBRACE)
        cases = []
        while self.peek().kind != TokenKind.RBRACE:
            case_val = self.parse_expression()
            self.expect(TokenKind.ARROW)
            case_stmt = self.parse_statement()
            cases.append((case_val, case_stmt))
        self.expect(TokenKind.RBRACE)
        return Switch(scrutinee, cases)

    def _parse_block(self):
        self.expect(TokenKind.LBRACE)
        stmts = []
        while self.peek().kind not in (TokenKind.RBRACE, TokenKind.EOF):
            stmts.append(self.parse_statement())
        self.expect(TokenKind.RBRACE)
        return Block(stmts)

    def _parse_ident_stmt(self):
        """解析 标识符语句 或 表达式语句，含 a = expr 和 a[idx] = expr"""
        expr = self.parse_expression()
        if self.peek().kind == TokenKind.EQ:
            self.advance()
            rhs = self.parse_expression()
            stmt = Assignment(expr, rhs)
        else:
            stmt = ExpressionStatement(expr)
        self.match(TokenKind.SEMI)
        return stmt

    # ========== 表达式（优先级链：逻辑或 > 逻辑与 > 比较 > 加减 > 乘除 > 前缀 > 后缀 > 基本）

    def parse_expression(self):
        return self.parse_logic_or()

    def parse_logic_or(self):
        left = self.parse_logic_and()
        while self.peek().kind == TokenKind.OR:
            op = self.advance().value
            right = self.parse_logic_and()
            left = BinaryOp(left, op, right)
        return left

    def parse_logic_and(self):
        left = self.parse_comparison()
        while self.peek().kind == TokenKind.AND:
            op = self.advance().value
            right = self.parse_comparison()
            left = BinaryOp(left, op, right)
        return left

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
        left = self.parse_unary()
        while self.peek().kind in (TokenKind.STAR, TokenKind.SLASH, TokenKind.PERCENT):
            op = self.advance().value
            right = self.parse_unary()
            left = BinaryOp(left, op, right)
        return left

    def parse_unary(self):
        """前缀一元运算符：! 等。"""
        if self.peek().kind == TokenKind.NOT:
            op = self.advance().value
            operand = self.parse_unary()
            return UnaryOp(op, operand)
        return self.parse_postfix()

    def parse_postfix(self):
        """处理 .field、(args)、[idx]、.method(args) 后缀。"""
        expr = self.parse_primary()
        while True:
            if self.peek().kind == TokenKind.LPAREN:
                start_expr = expr
                self.advance()
                args = []
                if self.peek().kind != TokenKind.RPAREN:
                    args.append(self.parse_expression())
                    while self.peek().kind == TokenKind.COMMA:
                        self.advance()
                        args.append(self.parse_expression())
                self.expect(TokenKind.RPAREN)
                if isinstance(start_expr, Identifier):
                    expr = FunctionCall(start_expr.name, args)
                    if hasattr(start_expr, "span"):
                        expr.span = (start_expr.span[0], self.tokens[self.pos - 1].pos)
                else:
                    raise ParseError("Only named functions and closure variables can be called")
            elif self.peek().kind == TokenKind.DOT:
                self.advance()
                field = self.expect(TokenKind.IDENT).value
                if self.peek().kind == TokenKind.LPAREN:
                    # 方法调用: obj.method(args)
                    self.advance()
                    args = []
                    if self.peek().kind != TokenKind.RPAREN:
                        args.append(self.parse_expression())
                        while self.peek().kind == TokenKind.COMMA:
                            self.advance()
                            args.append(self.parse_expression())
                    self.expect(TokenKind.RPAREN)
                    expr = MethodCall(expr, field, args)
                else:
                    expr = FieldAccess(expr, field)
            elif self.peek().kind == TokenKind.LBRACKET:
                self.advance()
                first = self.parse_expression()
                # arr[start:end] 切片 vs arr[idx] 索引
                if self.peek().kind == TokenKind.COLON:
                    self.advance()
                    if self.peek().kind == TokenKind.RBRACKET:
                        end = None
                    else:
                        end = self.parse_expression()
                    self.expect(TokenKind.RBRACKET)
                    expr = SliceExpr(expr, first, end)
                else:
                    self.expect(TokenKind.RBRACKET)
                    expr = IndexAccess(expr, first)
            else:
                break
        return expr

    def parse_primary(self):
        t = self.peek()

        if t.kind == TokenKind.IF:
            start = self.advance()
            condition = self.parse_expression()
            then_block = self._parse_block()
            else_block = None
            if self.peek().kind == TokenKind.ELSE:
                self.advance()
                if self.peek().kind == TokenKind.IF:
                    else_block = Block([ExpressionStatement(self.parse_primary())])
                else:
                    else_block = self._parse_block()
            return self.span(IfExpr(condition, then_block, else_block), start)

        if t.kind == TokenKind.LBRACE:
            start = self.peek()
            block = self._parse_block()
            return self.span(BlockExpr(block), start)

        if t.kind == TokenKind.STRING:
            start = self.advance()
            return self.span(StringLiteral(t.value), start)

        if t.kind == TokenKind.INTEGER:
            start = self.advance()
            return self.span(IntegerLiteral(t.value), start)

        if t.kind == TokenKind.BOOL:
            start = self.advance()
            return self.span(BoolLiteral(t.value), start)

        if t.kind == TokenKind.FUN:
            start = self.advance()
            return self._parse_function_expr(start)

        if t.kind == TokenKind.CHAR:
            self.advance()
            return IntegerLiteral(t.value)

        if t.kind == TokenKind.NEW:
            self.advance()
            name = self.expect(TokenKind.IDENT).value
            self.expect(TokenKind.LBRACE)
            fields = []
            if self.peek().kind != TokenKind.RBRACE:
                fname = self.expect(TokenKind.IDENT).value
                self.expect(TokenKind.COLON)
                fval = self.parse_expression()
                fields.append((fname, fval))
                while self.peek().kind == TokenKind.COMMA:
                    self.advance()
                    fname = self.expect(TokenKind.IDENT).value
                    self.expect(TokenKind.COLON)
                    fval = self.parse_expression()
                    fields.append((fname, fval))
            self.expect(TokenKind.RBRACE)
            return StructLiteral(name, fields, heap=True)

        if t.kind == TokenKind.IDENT:
            start = self.advance()
            name = start.value
            # EnumRef: Name::Variant
            if self.peek().kind == TokenKind.COLONCOLON:
                self.advance()
                variant = self.expect(TokenKind.IDENT).value
                return EnumRef(name, variant)
            # struct 字面量: Name { field: val, ... }
            # 前瞻避免混淆 if 块：需 { 后首个 IDENT 之后是 :
            if self.peek().kind == TokenKind.LBRACE:
                save = self.pos
                self.advance()  # 吞 {
                is_struct = False
                if self.peek().kind == TokenKind.RBRACE:
                    is_struct = True  # Name{}
                elif self.peek().kind == TokenKind.IDENT:
                    self.advance()
                    is_struct = self.peek().kind == TokenKind.COLON
                self.pos = save  # 回退
                if is_struct:
                    self.advance()  # 吞 {
                    fields = []
                    if self.peek().kind != TokenKind.RBRACE:
                        fname = self.expect(TokenKind.IDENT).value
                        self.expect(TokenKind.COLON)
                        fval = self.parse_expression()
                        fields.append((fname, fval))
                        while self.peek().kind == TokenKind.COMMA:
                            self.advance()
                            fname = self.expect(TokenKind.IDENT).value
                            self.expect(TokenKind.COLON)
                            fval = self.parse_expression()
                            fields.append((fname, fval))
                    self.expect(TokenKind.RBRACE)
                    return self.span(StructLiteral(name, fields), start)
            return self.span(Identifier(name), start)

        if t.kind == TokenKind.LBRACKET:
            # [N]T { e1, e2, ... } 数组字面量 / []T { ... } 切片字面量
            start = self.advance()  # 吞 [
            length = None
            if self.peek().kind != TokenKind.RBRACKET:
                length = self.expect(TokenKind.INTEGER).value
            self.expect(TokenKind.RBRACKET)
            elem_type = self.expect(TokenKind.IDENT).value
            self.expect(TokenKind.LBRACE)
            elements = []
            if self.peek().kind != TokenKind.RBRACE:
                elements.append(self.parse_expression())
                while self.peek().kind == TokenKind.COMMA:
                    self.advance()
                    elements.append(self.parse_expression())
            self.expect(TokenKind.RBRACE)
            if length is None:
                return self.span(SliceLiteral(elem_type, elements), start)
            return self.span(ArrayLiteral(length, elem_type, elements), start)

        if t.kind == TokenKind.LPAREN:
            self.advance()
            expr = self.parse_expression()
            self.expect(TokenKind.RPAREN)
            return expr

        raise ParseError(f"Unexpected token: {t}")


def parse(tokens: list[Token]) -> Program:
    return Parser(tokens).parse_program()
