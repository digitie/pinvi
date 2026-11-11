// 공통 구현 우회가 다시 유입되면 CI에서 실패한다.
import ts from 'typescript';
import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
const roots = ['components/admin', 'app/(admin)'];
function files(dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) =>
    entry.isDirectory()
      ? files(join(dir, entry.name))
      : /\.tsx?$/.test(entry.name) && !/\.test\./.test(entry.name)
        ? [join(dir, entry.name)]
        : [],
  );
}
const sources = roots.flatMap(files).map((path) => [path, readFileSync(path, 'utf8')]);
const errors = [];
for (const [path, source] of sources) {
  if (/from\s*["\x27]@base-ui\//.test(source)) errors.push(path + ': Base UI 직접 구현 금지');
  if (/<table(?:\s|>)/.test(source)) errors.push(path + ': 공통 VirtualTable 사용 필요');
  if (/from\s*["\x27]@tanstack\/react-(?:table|virtual)/.test(source))
    errors.push(path + ': 공통 table 계약 사용 필요');
}
const combined = sources.map(([, source]) => source).join('\n');
for (const pattern of [
  /useForm/,
  /zustand/,
  /@kor-travel\/ui(?:\/login-form)?["\x27]/,
  /@kor-travel\/ui\/virtual-table/,
]) {
  if (!pattern.test(combined)) errors.push('필수 공통 소비 또는 폼/상태 사용 누락: ' + pattern);
}
const fontSource = readFileSync('app/globals.css', 'utf8');
if (!fontSource.includes('@kor-travel/tokens/font.css'))
  errors.push('공통 Pretendard CSS 사용 필요');
const overlayEvents = new Set(['focusin', 'focusout', 'keydown', 'pointerdown']);

// 공개 Dialog/Popover에서도 공통 엔진을 우회하는 portal·전역 dismiss/focus engine을 막는다.
for (const path of ['components/ui', 'components/app', 'lib'].flatMap(files)) {
  const source = ts.createSourceFile(
    path,
    readFileSync(path, 'utf8'),
    ts.ScriptTarget.Latest,
    true,
    path.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS,
  );
  const portalNames = new Set();
  function visit(node) {
    if (ts.isImportDeclaration(node) && ts.isStringLiteral(node.moduleSpecifier)) {
      const importPath = node.moduleSpecifier.text;
      if (importPath.endsWith('/useModalDialog'))
        errors.push(path + ': 자체 modal engine 재도입 금지');
      const bindings = node.importClause?.namedBindings;
      if (importPath === 'react-dom' && bindings && ts.isNamedImports(bindings))
        for (const specifier of bindings.elements)
          if ((specifier.propertyName ?? specifier.name).text === 'createPortal')
            portalNames.add(specifier.name.text);
    }
    if (ts.isCallExpression(node)) {
      const expr = node.expression;
      if (
        (ts.isIdentifier(expr) && portalNames.has(expr.text)) ||
        (ts.isPropertyAccessExpression(expr) && expr.name.text === 'createPortal')
      )
        errors.push(path + ': 공통 Portal을 사용하세요');
      if (
        ts.isPropertyAccessExpression(expr) &&
        expr.name.text === 'addEventListener' &&
        ts.isIdentifier(expr.expression) &&
        expr.expression.text === 'document' &&
        node.arguments[0] &&
        ts.isStringLiteral(node.arguments[0]) &&
        overlayEvents.has(node.arguments[0].text)
      )
        errors.push(path + ': 전역 overlay 이벤트 대신 공통 Radix lifecycle 사용 필요');
    }
    ts.forEachChild(node, visit);
  }
  visit(source);
}
if (errors.length) {
  console.error(errors.join('\n'));
  process.exitCode = 1;
} else console.log('관리자/공개 공통 UI·단일 overlay 엔진 경계 일치');
