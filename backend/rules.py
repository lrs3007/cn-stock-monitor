"""A deliberately small expression language, interpreted without eval/exec.

REF and rolling functions operate in the argument's native timeframe.
Mixed timeframes align to the union of closed-bar timestamps, forward only.
Unknown data uses nullable Boolean semantics and never becomes a match.
"""
import ast
import operator
import numpy as np
import pandas as pd

from . import indicators
from .market import TIMEFRAMES

PRICE = {'OPEN': 'open', 'HIGH': 'high', 'LOW': 'low', 'CLOSE': 'close', 'VOLUME': 'volume', 'VOL': 'volume', 'AMOUNT': 'amount'}
SPECIAL = {'REF', 'HHV', 'LLV', 'SUM', 'AVG', 'COUNT', 'EVERY', 'EXIST', 'ABS', 'MAX', 'MIN', 'CROSSUP', 'CROSSDOWN'}


def parse(expression):
    if not expression or len(expression) > 4000:
        raise ValueError('条件表达式不能为空，且最多 4000 个字符')
    try:
        tree = ast.parse('(\n' + expression + '\n)', mode='eval')
    except (SyntaxError, RecursionError):
        raise ValueError('表达式语法有误，请检查括号、引号与 and/or') from None
    nodes = list(ast.walk(tree))
    if len(nodes)>300:
        raise ValueError('规则过于复杂，请拆分为多条规则')
    allowed = (ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.UnaryOp, ast.Not, ast.USub, ast.UAdd,
               ast.BinOp, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Compare, ast.Gt, ast.GtE, ast.Lt,
               ast.LtE, ast.Eq, ast.NotEq, ast.Call, ast.Name, ast.Load, ast.Constant, ast.keyword)
    for node in nodes:
        if not isinstance(node, allowed):
            raise ValueError('只允许指标、四则运算、比较和白名单函数；不支持任意代码')
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise ValueError('函数调用格式不正确')
            name = node.func.id
            if name not in PRICE and name not in SPECIAL:
                indicators.specification(name)
            if any(k.arg is None for k in node.keywords):
                raise ValueError('不支持展开参数')
        if isinstance(node, ast.Name) and node.id not in PRICE and node.id not in SPECIAL:
            indicators.specification(node.id)
        if isinstance(node, ast.Constant) and (type(node.value) not in [int, float, str, bool] or (isinstance(node.value,(int,float)) and abs(node.value)>1e12)):
            raise ValueError('不支持的常量')
    if not isinstance(tree.body, (ast.Compare, ast.BoolOp, ast.UnaryOp, ast.Call)):
        raise ValueError('规则必须产生布尔条件，例如 RSI(14) < 30')
    return tree


def align(a, b):
    if isinstance(a, pd.Series) and isinstance(b, pd.Series):
        index = a.index.union(b.index)
        # Fill newly introduced timestamps only; never hide a real missing value.
        return a.reindex(index, method='ffill'), b.reindex(index, method='ffill')
    return a, b


def numeric(value):
    if isinstance(value, pd.Series):
        if pd.api.types.is_bool_dtype(value.dtype):
            return value.astype('Float64')
        return value
    if type(value) not in [int, float]:
        raise ValueError('四则运算需要数值或指标序列')
    return value


def boolean(value):
    if isinstance(value, pd.Series) and pd.api.types.is_bool_dtype(value.dtype):
        return value.astype('boolean')
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    raise ValueError('条件需要比较运算（如 >、<），不能直接使用指标数值')


def comparison(a, b, op):
    a, b = align(a, b)
    result = op(a, b)
    if isinstance(result, pd.Series):
        valid = pd.Series(True, index=result.index)
        if isinstance(a,pd.Series): valid &= a.notna()
        if isinstance(b,pd.Series): valid &= b.notna()
        return result.astype('boolean').where(valid)
    return result


class Evaluator:
    def __init__(self, market):
        self.market = market
        self.evidence = {}
        self.cache = {}

    def visit(self, node):
        if isinstance(node, ast.Constant): return node.value
        if isinstance(node, ast.Expression): return self.visit(node.body)
        if isinstance(node, ast.BoolOp):
            values = [boolean(self.visit(v)) for v in node.values]
            result = values[0]
            for v in values[1:]:
                a,b = align(result,v)
                result = operator.and_(a,b) if isinstance(node.op,ast.And) else operator.or_(a,b)
            return result
        if isinstance(node, ast.UnaryOp):
            val = self.visit(node.operand)
            if isinstance(node.op,ast.Not):
                val = boolean(val)
                return ~val if isinstance(val,pd.Series) else not val
            return -numeric(val) if isinstance(node.op,ast.USub) else numeric(val)
        if isinstance(node, ast.BinOp):
            a,b = align(numeric(self.visit(node.left)), numeric(self.visit(node.right)))
            if isinstance(node.op, ast.Div):
                if isinstance(b,pd.Series): b=b.replace(0,np.nan)
                elif b==0: raise ValueError('除数不能为 0')
            result = {ast.Add:operator.add,ast.Sub:operator.sub,ast.Mult:operator.mul,ast.Div:operator.truediv}[type(node.op)](a,b)
            return result.replace([np.inf,-np.inf],np.nan) if isinstance(result,pd.Series) else result
        if isinstance(node, ast.Compare):
            a = self.visit(node.left)
            result = None
            for op,right in zip(node.ops,node.comparators):
                b=self.visit(right)
                item=comparison(a,b,{ast.Gt:operator.gt,ast.GtE:operator.ge,ast.Lt:operator.lt,ast.LtE:operator.le,ast.Eq:operator.eq,ast.NotEq:operator.ne}[type(op)])
                result=item if result is None else operator.and_(*align(result,item))
                a=b
            return result
        if not isinstance(node,ast.Call):
            raise ValueError('指标必须带括号，例如 CLOSE() 或 RSI(14)')
        name=node.func.id
        args=[self.visit(a) for a in node.args]
        if len({k.arg for k in node.keywords}) != len(node.keywords):
            raise ValueError('不允许重复的关键字参数')
        kwargs={k.arg:self.visit(k.value) for k in node.keywords}
        if name in SPECIAL:
            if kwargs: raise ValueError(f'{name} 不接受关键字参数')
            expected=1 if name=='ABS' else 2
            if len(args)!=expected: raise ValueError(f'{name} 需要 {expected} 个参数')
            a=args[0]
            if name=='ABS': return abs(numeric(a))
            b=args[1]
            if name in ['MAX','MIN']:
                a,b=align(numeric(a),numeric(b))
                return np.maximum(a,b) if name=='MAX' else np.minimum(a,b)
            if name in ['CROSSUP','CROSSDOWN']:
                a,b=align(numeric(a),numeric(b))
                if not isinstance(a,pd.Series) and not isinstance(b,pd.Series):
                    raise ValueError('交叉函数至少需要一条序列')
                pa=a.shift() if isinstance(a,pd.Series) else a
                pb=b.shift() if isinstance(b,pd.Series) else b
                return (comparison(a,b,operator.gt)&comparison(pa,pb,operator.le)) if name=='CROSSUP' else (comparison(a,b,operator.lt)&comparison(pa,pb,operator.ge))
            if not isinstance(a,pd.Series) or type(b) is not int or not 1<=b<=1000:
                raise ValueError(f'{name} 需要序列和 1–1000 的整数周期')
            if name=='REF': return a.shift(b)
            if name in ['COUNT','EVERY','EXIST']:
                vals=boolean(a).astype('Float64').rolling(b,min_periods=b).sum()
                if name=='COUNT': return vals
                return (vals.eq(b) if name=='EVERY' else vals.gt(0)).astype('boolean').where(vals.notna())
            return getattr(numeric(a).rolling(b), {'HHV':'max','LLV':'min','SUM':'sum','AVG':'mean'}[name])()
        tf=kwargs.pop('tf','1d')
        line=kwargs.pop('line',None)
        if tf not in TIMEFRAMES: raise ValueError('不支持的周期：'+str(tf))
        key=ast.unparse(node)
        if key in self.cache: return self.cache[key]
        frame=self.market.bars(tf)
        if name in PRICE:
            if args or kwargs or line: raise ValueError(f'{name} 仅接受 tf 参数')
            result=frame[PRICE[name]]
        else:
            if name=='VWAP' and not tf.endswith('m'):
                raise ValueError('VWAP 为日内指标，请选择分钟周期')
            result=indicators.series(frame,name,args,kwargs,line)
        self.cache[key]=result
        val=result.iloc[-1] if len(result) else np.nan
        self.evidence[key]={'value':float(val) if pd.notna(val) and np.isfinite(val) else None,
                            'time':str(result.index[-1]) if len(result) else None}
        return result

    def run(self, expression):
        value=boolean(self.visit(parse(expression)))
        if isinstance(value,pd.Series):
            value=value[value.index<=self.market.asof]
            last=value.iloc[-1] if len(value) else pd.NA
            stamp=str(value.index[-1]) if len(value) else None
        else:
            last,stamp=value,str(self.market.asof)
        return {'matched':bool(last) if pd.notna(last) else False, 'ready':bool(pd.notna(last)),
                'bar_time':stamp, 'evidence':self.evidence,
                'reason':None if pd.notna(last) else '历史数据不足或存在缺失值，暂不产生信号'}
