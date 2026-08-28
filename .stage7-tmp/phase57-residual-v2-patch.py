from pathlib import Path

path = Path('/tmp/phase57-residual-binding-install.py')
body = path.read_text(encoding='utf-8')
needle = '''@dataclass(frozen=True, slots=True)
class QueryBinding:
    symbol_id: str
    subject_id: str
    component: str | None
'''
replacement = '''@dataclass(frozen=True, slots=True)
class QueryBinding:
    symbol_id: str
    subject_id: str
    component: str | None

    def __iter__(self):
        yield self.symbol_id
        yield self.subject_id
        yield self.component
'''
if needle not in body:
    raise SystemExit('query_binding_dataclass_anchor_missing')
path.write_text(body.replace(needle, replacement, 1), encoding='utf-8')
