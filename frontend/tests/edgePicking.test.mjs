import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import ts from 'typescript';

const source = fs.readFileSync(new URL('../src/edgePicking.ts', import.meta.url), 'utf8');
const code = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText;
const { nearestProjectedEdge } = await import('data:text/javascript;base64,' + Buffer.from(code).toString('base64'));
const edge = (id, points) => ({ id, points: points.map(([x, y]) => ({ x, y })) });

test('thin operation curves get a constant 16 pixel target at different projected scales', () => {
  for (const length of [20, 200, 2000]) {
    const paths = [edge('operation', [[0, 0], [length, 0]])];
    assert.equal(nearestProjectedEdge({ x: length / 2, y: 15.9 }, paths), 'operation');
    assert.equal(nearestProjectedEdge({ x: length / 2, y: 16 }, paths), 'operation');
    assert.equal(nearestProjectedEdge({ x: length / 2, y: 16.1 }, paths), null);
  }
});

test('picking follows curved polyline segments rather than the shortcut between endpoints', () => {
  const paths = [edge('arc', [[0, 0], [50, 50], [100, 0]])];
  assert.equal(nearestProjectedEdge({ x: 50, y: 48 }, paths), 'arc');
  assert.equal(nearestProjectedEdge({ x: 50, y: 0 }, paths), null);
  assert.equal(nearestProjectedEdge({ x: -17, y: 0 }, paths), null);
  assert.equal(nearestProjectedEdge({ x: -16, y: 0 }, paths), 'arc');
});

test('crossing and overlapping paths pick nearest, with stable identity at exact ties', () => {
  const paths = [edge('z', [[0, 0], [100, 0]]), edge('a', [[0, 10], [100, 10]])];
  assert.equal(nearestProjectedEdge({ x: 40, y: 2 }, paths), 'z');
  assert.equal(nearestProjectedEdge({ x: 40, y: 8 }, paths), 'a');
  assert.equal(nearestProjectedEdge({ x: 40, y: 5 }, paths), 'a');
  assert.equal(nearestProjectedEdge({ x: 40, y: 5 }, [...paths].reverse()), 'a');
});

test('nonfinite points split paths and invalid pointer or radius cannot select an edge', () => {
  const paths = [edge('split', [[0, 0], [NaN, NaN], [100, 0]])];
  assert.equal(nearestProjectedEdge({ x: 50, y: 0 }, paths), null);
  const valid = [edge('ok', [[0, 0], [100, 0]])];
  for (const point of [{ x: Infinity, y: 0 }, { x: 0, y: NaN }]) {
    assert.equal(nearestProjectedEdge(point, valid), null);
  }
  for (const radius of [-1, NaN, Infinity]) {
    assert.equal(nearestProjectedEdge({ x: 50, y: 0 }, valid, radius), null);
  }
  const partial = [edge('partial', [[0, Infinity], [0, 0], [100, 0]])];
  assert.equal(nearestProjectedEdge({ x: 50, y: 4 }, partial), 'partial');
});

test('empty and single-point paths are ignored, degenerate segments and zero radius are defined', () => {
  assert.equal(nearestProjectedEdge({ x: 0, y: 0 }, []), null);
  assert.equal(nearestProjectedEdge({ x: 0, y: 0 }, [edge('empty', []), edge('one', [[0, 0]])]), null);
  const paths = [edge('zero', [[10, 20], [10, 20]])];
  assert.equal(nearestProjectedEdge({ x: 10, y: 20 }, paths, 0), 'zero');
  assert.equal(nearestProjectedEdge({ x: 10, y: 20.01 }, paths, 0), null);
});
