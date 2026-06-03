"""递归下降解析器 —— Token 流 → AST。"""

from compiler.ast import *
from compiler.lexer import Token, TokenKind


class ParseError(Exception):
    pass


class Parser:
    def __init__(self, tokens: list[Token], imported_modules: set[str] | None = None):
        self.tokens = tokens
        self.pos = 0
        self.imported_modules = imported_modules or set()

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
            if self.peek().kind == TokenKind.IMPORT:
                stmts.append(self._parse_import())
                continue
            if self.peek().kind == TokenKind.TYPE:
                stmts.append(self._parse_type_alias())
                continue
            if self.peek().kind == TokenKind.EXTERN:
                stmts.append(self._parse_extern_block())
                continue
            if self.peek().kind == TokenKind.IFACE:
                stmts.append(self._parse_iface())
                continue
            stmts.append(self.parse_statement())
        return Program(stmts)

    # ========== 语句 ==========

    def parse_statement(self):
        t = self.peek()

        if t.kind == TokenKind.IMPORT:
            raise ParseError("import is only allowed at top level")
        if t.kind == TokenKind.EXTERN:
            raise ParseError("extern is only allowed at top level")
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
        if t.kind == TokenKind.IFACE:
            raise ParseError("iface is only allowed at top level")
        if t.kind == TokenKind.FOR:
            return self._parse_for()
        if t.kind == TokenKind.TRY:
            return self._parse_try()
        if t.kind == TokenKind.THROW:
            return self._parse_throw()
        if t.kind == TokenKind.DEFER:
            return self._parse_defer()
        if t.kind == TokenKind.TYPE:
            raise ParseError("type alias is only allowed at top level")
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

    def _parse_type_alias(self):
        start = self.advance()
        name = self.expect(TokenKind.IDENT).value
        self.expect(TokenKind.EQ)
        target = self._parse_type()
        stmt = self.span(TypeAlias(name, target), start)
        self.match(TokenKind.SEMI)
        return stmt

    def _parse_import(self):
        start = self.advance()
        name = self.expect(TokenKind.IDENT).value
        if self.peek().kind == TokenKind.DOT:
            raise ParseError("import v1 only supports one-level module names")
        if self.peek().kind == TokenKind.LBRACE:
            raise ParseError("selective import is not supported in import v1")
        stmt = self.span(ImportDecl(name), start)
        self.match(TokenKind.SEMI)
        return stmt

    def _parse_extern_block(self):
        start = self.advance()
        lib = None
        if self.peek().kind == TokenKind.STRING:
            lib = self.advance().value
        self.expect(TokenKind.LBRACE)
        funcs = []
        while self.peek().kind != TokenKind.RBRACE:
            if self.peek().kind == TokenKind.EOF:
                raise ParseError("unterminated extern block")
            if self.peek().kind != TokenKind.FUN:
                raise ParseError("extern block only allows function declarations")
            fn = self._parse_function_signature_only()
            fn.is_extern = True
            fn.extern_lib = lib
            funcs.append(fn)
            self.match(TokenKind.SEMI)
        self.expect(TokenKind.RBRACE)
        self.match(TokenKind.SEMI)
        return self.span(ExternBlock(lib, funcs), start)

    def _parse_type(self) -> str:
        if self.peek().kind == TokenKind.QUESTION:
            self.advance()
            self.expect(TokenKind.STAR)
            return "?*" + self._parse_type()
        if self.peek().kind == TokenKind.FUN:
            self.advance()
            self.expect(TokenKind.LPAREN)
            params = []
            if self.peek().kind != TokenKind.RPAREN:
                params.append(self._parse_type())
                while self.peek().kind == TokenKind.COMMA:
                    self.advance()
                    params.append(self._parse_type())
            self.expect(TokenKind.RPAREN)
            ret = self._parse_type()
            return f"fn({','.join(params)})->{ret}"
        if self.peek().kind == TokenKind.LPAREN:
            raise ParseError("old function type syntax is not supported; use fun(T) R")
        if self.peek().kind == TokenKind.STAR:
            self.advance()
            return "*" + self._parse_type()
        if self.peek().kind == TokenKind.LBRACKET:
            self.advance()
            length = None
            if self.peek().kind != TokenKind.RBRACKET:
                length_value = self.expect(TokenKind.INTEGER).value
                length, suffix = length_value if isinstance(length_value, tuple) else (length_value, None)
                if suffix is not None:
                    raise ParseError("array length literal cannot have a type suffix")
            self.expect(TokenKind.RBRACKET)
            elem = self._parse_type()
            return f"[]{elem}" if length is None else f"[{length}]{elem}"
        name = self.expect(TokenKind.IDENT).value
        if self.peek().kind == TokenKind.DOT:
            self.advance()
            name = f"{name}.{self.expect(TokenKind.IDENT).value}"
        if self.peek().kind == TokenKind.LBRACKET:
            args = self._parse_type_arg_list()
            return f"{name}[{','.join(args)}]"
        return name

    def _parse_type_arg_list(self) -> list[str]:
        self.expect(TokenKind.LBRACKET)
        args = []
        if self.peek().kind != TokenKind.RBRACKET:
            args.append(self._parse_type())
            while self.peek().kind == TokenKind.COMMA:
                self.advance()
                args.append(self._parse_type())
        self.expect(TokenKind.RBRACKET)
        return args

    def _parse_type_params(self) -> list[str]:
        if self.peek().kind != TokenKind.LBRACKET:
            return []
        self.advance()
        params = []
        if self.peek().kind != TokenKind.RBRACKET:
            while True:
                name = self.expect(TokenKind.IDENT).value
                if self.peek().kind == TokenKind.IDENT:
                    constraint = self.advance().value
                    if constraint != "any":
                        raise ParseError("generic v1 only supports any constraints")
                params.append(name)
                if self.peek().kind != TokenKind.COMMA:
                    break
                self.advance()
        self.expect(TokenKind.RBRACKET)
        return params

    def _parse_param(self, *, allow_default: bool) -> Param:
        pname = self.expect(TokenKind.IDENT).value
        self.expect(TokenKind.COLON)
        ptype = self._parse_type()
        default = None
        if self.peek().kind == TokenKind.EQ:
            if not allow_default:
                raise ParseError("default parameters are not supported here")
            self.advance()
            default = self.parse_expression()
        return Param(pname, ptype, default)

    def _parse_param_list(self, *, allow_default: bool) -> list[Param]:
        params = []
        if self.peek().kind != TokenKind.RPAREN:
            params.append(self._parse_param(allow_default=allow_default))
            while self.peek().kind == TokenKind.COMMA:
                self.advance()
                if not allow_default and self.peek().kind in (TokenKind.DOT, TokenKind.DOTDOT):
                    raise ParseError("extern v1 does not support varargs")
                params.append(self._parse_param(allow_default=allow_default))
        return params

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
        type_params = self._parse_type_params()
        self.expect(TokenKind.LPAREN)
        params = self._parse_param_list(allow_default=True)
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
                                   receiver_name, receiver_type, return_type_explicit, type_params)

    def _parse_function_signature_only(self):
        self.advance()  # fun
        if self.peek().kind == TokenKind.LPAREN:
            raise ParseError("extern methods are not supported")
        name = self.expect(TokenKind.IDENT).value
        type_params = self._parse_type_params()
        if type_params:
            raise ParseError("generic extern functions are not supported")
        self.expect(TokenKind.LPAREN)
        params = self._parse_param_list(allow_default=False)
        self.expect(TokenKind.RPAREN)
        return_type = None
        return_type_explicit = False
        if self.peek().kind == TokenKind.COLON:
            self.advance()
            return_type = self._parse_type()
            return_type_explicit = True
        extern_symbol = None
        if self.peek().kind == TokenKind.EQ:
            self.advance()
            extern_symbol = self.expect(TokenKind.STRING).value
        if self.peek().kind == TokenKind.LBRACE:
            raise ParseError("extern function bodies are not supported")
        fn = FunctionDeclaration(name, params, return_type, Block([]),
                                 return_type_explicit=return_type_explicit)
        fn.extern_symbol = extern_symbol
        return fn

    def _parse_function_expr(self, start):
        self.expect(TokenKind.LPAREN)
        params = self._parse_param_list(allow_default=False)
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
            return ForCondition(condition, body)

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
        return ForCondition(condition, body)

    def _parse_struct(self):
        self.advance()  # 吞 struct
        name = self.expect(TokenKind.IDENT).value
        type_params = self._parse_type_params()
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
        stmt = StructDecl(name, fields, type_params)
        self.match(TokenKind.SEMI)
        return stmt

    def _parse_iface(self):
        self.advance()
        name = self.expect(TokenKind.IDENT).value
        self.expect(TokenKind.LBRACE)
        methods = []
        embeds = []
        while self.peek().kind != TokenKind.RBRACE:
            if self.peek().kind == TokenKind.EOF:
                raise ParseError("unterminated iface declaration")
            if self.peek().kind == TokenKind.FUN:
                self.advance()
                if self.peek().kind == TokenKind.LPAREN:
                    raise ParseError("iface methods cannot have receivers")
                mname = self.expect(TokenKind.IDENT).value
                self.expect(TokenKind.LPAREN)
                params = self._parse_param_list(allow_default=False)
                self.expect(TokenKind.RPAREN)
                ret = "void"
                if self.peek().kind == TokenKind.COLON:
                    self.advance()
                    ret = self._parse_type()
                if self.peek().kind == TokenKind.LBRACE:
                    raise ParseError("iface method declarations cannot have bodies")
                methods.append((mname, params, ret))
                self.match(TokenKind.SEMI)
                continue
            embeds.append(self._parse_type())
            self.match(TokenKind.SEMI)
        self.expect(TokenKind.RBRACE)
        stmt = IfaceDecl(name, methods, embeds)
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
        assign_ops = {
            TokenKind.EQ, TokenKind.PLUSEQ, TokenKind.MINUSEQ, TokenKind.STAREQ,
            TokenKind.SLASHEQ, TokenKind.PERCENTEQ, TokenKind.AMPEQ, TokenKind.PIPEEQ,
            TokenKind.CARETEQ, TokenKind.SHLEQ, TokenKind.SHREQ,
        }
        if self.peek().kind in assign_ops:
            op = self.advance().value
            rhs = self.parse_expression()
            stmt = Assignment(expr, rhs, op)
        elif self.peek().kind in (TokenKind.PLUSPLUS, TokenKind.MINUSMINUS):
            op = self.advance().value
            stmt = Update(expr, op)
        else:
            stmt = ExpressionStatement(expr)
        self.match(TokenKind.SEMI)
        return stmt

    # ========== 表达式（优先级链：逻辑或 > 逻辑与 > 比较 > Go 风格加减位或异或 > 乘除移位位与 > 前缀 > 后缀 > 基本）

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
        while self.peek().kind in (TokenKind.PLUS, TokenKind.MINUS, TokenKind.PIPE, TokenKind.CARET):
            op = self.advance().value
            right = self.parse_multiplicative()
            left = BinaryOp(left, op, right)
        return left

    def parse_multiplicative(self):
        left = self.parse_unary()
        while self.peek().kind in (TokenKind.STAR, TokenKind.SLASH, TokenKind.PERCENT, TokenKind.SHL, TokenKind.SHR, TokenKind.AMP):
            op = self.advance().value
            right = self.parse_unary()
            left = BinaryOp(left, op, right)
        return left

    def parse_unary(self):
        """前缀一元运算符：! 等。"""
        if self.peek().kind in (TokenKind.NOT, TokenKind.TILDE, TokenKind.MINUS):
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
                if isinstance(start_expr, Identifier) and start_expr.name == "size_of":
                    type_name = self._parse_type()
                    self.expect(TokenKind.RPAREN)
                    expr = SizeOfType(type_name)
                    if hasattr(start_expr, "span"):
                        expr.span = (start_expr.span[0], self.tokens[self.pos - 1].pos)
                    continue
                args = []
                if self.peek().kind != TokenKind.RPAREN:
                    args.append(self.parse_expression())
                    while self.peek().kind == TokenKind.COMMA:
                        self.advance()
                        args.append(self.parse_expression())
                self.expect(TokenKind.RPAREN)
                if isinstance(start_expr, Identifier):
                    expr = FunctionCall(start_expr.name, args, getattr(start_expr, "generic_type_args", []))
                    if hasattr(start_expr, "span"):
                        expr.span = (start_expr.span[0], self.tokens[self.pos - 1].pos)
                else:
                    raise ParseError("Only named functions and closure variables can be called")
            elif self.peek().kind == TokenKind.LBRACKET:
                save = self.pos
                if isinstance(expr, Identifier) and self._token_after_matching_bracket(self.pos).kind == TokenKind.LPAREN:
                    type_args = self._parse_type_arg_list()
                    expr.generic_type_args = type_args
                else:
                    self.pos = save
                    self.advance()
                    first = self.parse_expression()
                    if self.peek().kind == TokenKind.COLON:
                        self.advance()
                        end = None if self.peek().kind == TokenKind.RBRACKET else self.parse_expression()
                        self.expect(TokenKind.RBRACKET)
                        expr = SliceExpr(expr, first, end)
                    else:
                        self.expect(TokenKind.RBRACKET)
                        expr = IndexAccess(expr, first)
            elif self.peek().kind == TokenKind.DOT:
                start_pos = getattr(expr, "span", (self.peek().pos, self.peek().pos))[0]
                self.advance()
                field = self.expect(TokenKind.IDENT).value
                if (self.peek().kind == TokenKind.LBRACKET and isinstance(expr, Identifier)
                        and self.pos + 1 < len(self.tokens)
                        and self.tokens[self.pos + 1].kind != TokenKind.INTEGER):
                    qname = f"{expr.name}.{field}"
                    type_args = self._parse_type_arg_list()
                    if self.peek().kind == TokenKind.LPAREN:
                        self.advance()
                        args = []
                        if self.peek().kind != TokenKind.RPAREN:
                            args.append(self.parse_expression())
                            while self.peek().kind == TokenKind.COMMA:
                                self.advance()
                                args.append(self.parse_expression())
                        self.expect(TokenKind.RPAREN)
                        expr = FunctionCall(qname, args, type_args)
                    elif self.peek().kind == TokenKind.LBRACE:
                        self.advance()
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
                        expr = StructLiteral(f"{qname}[{','.join(type_args)}]", fields)
                    else:
                        raise ParseError("generic type application must be used in a call or struct literal")
                elif self.peek().kind == TokenKind.LPAREN:
                    self.advance()
                    args = []
                    if self.peek().kind != TokenKind.RPAREN:
                        args.append(self.parse_expression())
                        while self.peek().kind == TokenKind.COMMA:
                            self.advance()
                            args.append(self.parse_expression())
                    self.expect(TokenKind.RPAREN)
                    if isinstance(expr, Identifier) and expr.name in self.imported_modules:
                        expr = FunctionCall(f"{expr.name}.{field}", args)
                    else:
                        expr = MethodCall(expr, field, args)
                    expr.span = (start_pos, self.tokens[self.pos - 1].pos)
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

    def _token_after_matching_bracket(self, start_pos: int):
        depth = 0
        i = start_pos
        while i < len(self.tokens):
            kind = self.tokens[i].kind
            if kind == TokenKind.LBRACKET:
                depth += 1
            elif kind == TokenKind.RBRACKET:
                depth -= 1
                if depth == 0:
                    return self.tokens[i + 1] if i + 1 < len(self.tokens) else self.tokens[i]
            i += 1
        return self.tokens[start_pos]

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

        if t.kind == TokenKind.MATCH:
            start = self.advance()
            scrutinee = self.parse_expression()
            self.expect(TokenKind.LBRACE)
            arms = []
            while self.peek().kind != TokenKind.RBRACE:
                if self.peek().kind == TokenKind.ELSE:
                    self.advance()
                    pattern = None
                else:
                    pattern = self.parse_expression()
                self.expect(TokenKind.ARROW)
                body = self.parse_expression()
                arms.append((pattern, body))
                self.match(TokenKind.SEMI)
            self.expect(TokenKind.RBRACE)
            return self.span(MatchExpr(scrutinee, arms), start)

        if t.kind == TokenKind.LBRACE:
            start = self.peek()
            block = self._parse_block()
            return self.span(BlockExpr(block), start)

        if t.kind == TokenKind.STRING:
            start = self.advance()
            if isinstance(t.value, tuple) and t.value[0] == "interpolated":
                return self.span(InterpolatedString(self._parse_interpolated_parts(t.value[1])), start)
            return self.span(StringLiteral(t.value), start)

        if t.kind == TokenKind.INTEGER:
            start = self.advance()
            value, suffix = t.value if isinstance(t.value, tuple) else (t.value, None)
            return self.span(IntegerLiteral(value, suffix), start)

        if t.kind == TokenKind.FLOAT:
            start = self.advance()
            value, suffix = t.value
            return self.span(FloatLiteral(value, suffix), start)

        if t.kind == TokenKind.BOOL:
            start = self.advance()
            return self.span(BoolLiteral(t.value), start)

        if t.kind == TokenKind.NIL:
            start = self.advance()
            return self.span(NilLiteral(), start)

        if t.kind == TokenKind.FUN:
            start = self.advance()
            return self._parse_function_expr(start)

        if t.kind == TokenKind.CHAR:
            start = self.advance()
            return self.span(RuneLiteral(t.value), start)

        if t.kind == TokenKind.NEW:
            self.advance()
            name = self.expect(TokenKind.IDENT).value
            if self.peek().kind == TokenKind.DOT:
                self.advance()
                name = f"{name}.{self.expect(TokenKind.IDENT).value}"
            if self.peek().kind == TokenKind.LBRACKET:
                name = f"{name}[{','.join(self._parse_type_arg_list())}]"
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
            if (self.peek().kind == TokenKind.DOT
                    and self.pos + 2 < len(self.tokens)
                    and self.tokens[self.pos + 1].kind == TokenKind.IDENT
                    and self.tokens[self.pos + 2].kind in (TokenKind.COLONCOLON, TokenKind.LBRACE)):
                self.advance()
                qname = f"{name}.{self.expect(TokenKind.IDENT).value}"
                if self.peek().kind == TokenKind.COLONCOLON:
                    self.advance()
                    variant = self.expect(TokenKind.IDENT).value
                    return EnumRef(qname, variant)
                if self.peek().kind == TokenKind.LBRACE:
                    self.advance()
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
                    return self.span(StructLiteral(qname, fields), start)
                return self.span(Identifier(qname), start)
            # EnumRef: Name::Variant
            if self.peek().kind == TokenKind.COLONCOLON:
                self.advance()
                variant = self.expect(TokenKind.IDENT).value
                return EnumRef(name, variant)
            # struct 字面量: Name { field: val, ... }
            if (self.peek().kind == TokenKind.LBRACKET
                    and self._token_after_matching_bracket(self.pos).kind in (TokenKind.LPAREN, TokenKind.LBRACE)):
                save = self.pos
                type_args = self._parse_type_arg_list()
                if self.peek().kind == TokenKind.LPAREN:
                    self.advance()
                    args = []
                    if self.peek().kind != TokenKind.RPAREN:
                        args.append(self.parse_expression())
                        while self.peek().kind == TokenKind.COMMA:
                            self.advance()
                            args.append(self.parse_expression())
                    self.expect(TokenKind.RPAREN)
                    return self.span(FunctionCall(name, args, type_args), start)
                if self.peek().kind == TokenKind.LBRACE:
                    name = f"{name}[{','.join(type_args)}]"
                else:
                    self.pos = save
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
                length_value = self.expect(TokenKind.INTEGER).value
                length, suffix = length_value if isinstance(length_value, tuple) else (length_value, None)
                if suffix is not None:
                    raise ParseError("array length literal cannot have a type suffix")
            self.expect(TokenKind.RBRACKET)
            elem_type = self._parse_type()
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

    def _parse_interpolated_parts(self, raw_parts):
        from compiler.lexer import lex
        parts = []
        for kind, value in raw_parts:
            if kind == "literal":
                parts.append(StringLiteral(value))
            elif kind == "expr":
                expr_tokens = list(lex(value))
                expr_parser = Parser(expr_tokens, self.imported_modules)
                expr = expr_parser.parse_expression()
                expr_parser.expect(TokenKind.EOF)
                parts.append(expr)
            else:
                raise ParseError(f"unknown interpolated string part {kind}")
        return parts


def _scan_imports(tokens: list[Token]) -> set[str]:
    imports = set()
    for i, tok in enumerate(tokens[:-1]):
        if tok.kind == TokenKind.IMPORT and tokens[i + 1].kind == TokenKind.IDENT:
            imports.add(tokens[i + 1].value)
    return imports


def parse(tokens: list[Token], imported_modules: set[str] | None = None) -> Program:
    return Parser(tokens, imported_modules or _scan_imports(tokens)).parse_program()
