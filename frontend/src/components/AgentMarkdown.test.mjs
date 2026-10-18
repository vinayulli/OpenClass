import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import AgentMarkdown from './AgentMarkdown.js';

test('renders Markdown structure and preserves Python indentation',()=>{
  const html=renderToStaticMarkup(React.createElement(AgentMarkdown,null,'### Example\n\n**Encapsulation**\n\n```python\nclass Account:\n    pass\n```\n\n- One\n- Two'));
  assert.match(html,/<h3>Example<\/h3>/);
  assert.match(html,/<strong>Encapsulation<\/strong>/);
  assert.match(html,/class Account:\n    pass/);
  assert.match(html,/Copy code/);
  assert.match(html,/<ul>/);
});
test('blocks raw HTML, unsafe links and remote tracking images',()=>{
  const html=renderToStaticMarkup(React.createElement(AgentMarkdown,null,'<script>alert(1)</script>\n\n[bad](javascript:alert)\n\n![tracker](https://example.com/pixel)\n\n[good](https://example.com)'));
  assert.doesNotMatch(html,/<script|javascript:|<img/);
  assert.match(html,/href="https:\/\/example.com"/);
  assert.match(html,/noopener noreferrer/);
});
