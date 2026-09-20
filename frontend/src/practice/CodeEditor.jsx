import React, { useEffect, useId, useRef } from 'react';
import { defaultKeymap, history, historyKeymap, indentWithTab } from '@codemirror/commands';
import {
  bracketMatching,
  HighlightStyle,
  indentOnInput,
  indentUnit,
  syntaxHighlighting,
} from '@codemirror/language';
import { Annotation, Compartment, EditorSelection, EditorState } from '@codemirror/state';
import {
  drawSelection,
  EditorView,
  highlightActiveLine,
  highlightActiveLineGutter,
  highlightSpecialChars,
  keymap,
  lineNumbers,
} from '@codemirror/view';
import { python } from '@codemirror/lang-python';
import { tags } from '@lezer/highlight';
import './editor.css';

const pythonHighlightStyle = HighlightStyle.define([
  { tag: tags.comment, color: '#8b949e', fontStyle: 'italic' },
  { tag: [tags.keyword, tags.modifier, tags.operatorKeyword], color: '#ff7b72' },
  { tag: [tags.definition(tags.variableName), tags.function(tags.variableName)], color: '#d2a8ff' },
  { tag: [tags.variableName, tags.propertyName], color: '#e6edf3' },
  { tag: [tags.string, tags.special(tags.string)], color: '#a5d6ff' },
  { tag: [tags.number, tags.bool, tags.null], color: '#79c0ff' },
  { tag: [tags.operator, tags.punctuation], color: '#c9d1d9' },
  { tag: [tags.typeName, tags.className, tags.namespace], color: '#ffa657' },
  { tag: tags.invalid, color: '#ff7b72', textDecoration: 'underline' },
]);
const externalValueUpdate = Annotation.define();

function insertPythonIndentedNewline(view) {
  if (view.state.readOnly) return false;
  const transaction = view.state.changeByRange((range) => {
    const line = view.state.doc.lineAt(range.from);
    const beforeCursor = view.state.doc.sliceString(line.from, range.from);
    const leadingWhitespace = beforeCursor.match(/^\s*/)?.[0] ?? '';
    const indentation = beforeCursor.trimEnd().endsWith(':')
      ? `${leadingWhitespace}    `
      : leadingWhitespace;
    const insert = `\n${indentation}`;
    return {
      changes: { from: range.from, to: range.to, insert },
      range: EditorSelection.cursor(range.from + insert.length),
    };
  });
  view.dispatch(transaction);
  return true;
}

function lockedExtensions({ disabled, label, readOnly }) {
  const locked = readOnly || disabled;
  return [
    EditorState.readOnly.of(locked),
    EditorView.editable.of(!locked),
    EditorView.contentAttributes.of({
      'aria-disabled': disabled ? 'true' : 'false',
      'aria-label': label,
      'aria-readonly': locked ? 'true' : 'false',
      role: 'textbox',
      spellcheck: 'false',
      tabindex: disabled ? '-1' : '0',
    }),
  ];
}

/**
 * Controlled Python editor used by PracticeScreen.
 *
 * Tab and Shift+Tab indent/outdent like a coding IDE. Pressing Escape before
 * Tab temporarily restores browser focus navigation. Enter applies
 * Python-aware indentation, and undo/redo use the platform shortcuts.
 */
export default function CodeEditor({
  value,
  onChange,
  readOnly = false,
  disabled = false,
  readOnlyMessage = 'Editing is disabled after your learner quota is used.',
}) {
  const editorHostRef = useRef(null);
  const editorViewRef = useRef(null);
  const onChangeRef = useRef(onChange);
  const lockCompartmentRef = useRef(new Compartment());
  const label = 'Your Python solution';
  const descriptionId = useId();

  onChangeRef.current = onChange;

  useEffect(() => {
    if (!editorHostRef.current) return undefined;

    const view = new EditorView({
      parent: editorHostRef.current,
      state: EditorState.create({
        doc: value ?? '',
        extensions: [
          lineNumbers(),
          highlightActiveLineGutter(),
          highlightSpecialChars(),
          history(),
          drawSelection(),
          indentOnInput(),
          syntaxHighlighting(pythonHighlightStyle),
          bracketMatching(),
          highlightActiveLine(),
          keymap.of([
            { key: 'Enter', run: insertPythonIndentedNewline },
            indentWithTab,
            ...defaultKeymap,
            ...historyKeymap,
          ]),
          indentUnit.of('    '),
          python(),
          EditorView.contentAttributes.of({ 'aria-describedby': descriptionId }),
          EditorView.updateListener.of((update) => {
            const comesFromValueProp = update.transactions.some(
              (transaction) => transaction.annotation(externalValueUpdate),
            );
            if (update.docChanged && !comesFromValueProp) {
              onChangeRef.current?.(update.state.doc.toString());
            }
          }),
          lockCompartmentRef.current.of(lockedExtensions({ disabled, label, readOnly })),
        ],
      }),
    });

    editorViewRef.current = view;
    return () => {
      editorViewRef.current = null;
      view.destroy();
    };
  }, []);

  useEffect(() => {
    const view = editorViewRef.current;
    const nextValue = value ?? '';
    if (!view || view.state.doc.toString() === nextValue) return;

    view.dispatch({
      changes: { from: 0, to: view.state.doc.length, insert: nextValue },
      annotations: externalValueUpdate.of(true),
    });
  }, [value]);

  useEffect(() => {
    const view = editorViewRef.current;
    if (!view) return;
    view.dispatch({
      effects: lockCompartmentRef.current.reconfigure(lockedExtensions({ disabled, label, readOnly })),
    });
  }, [disabled, readOnly]);

  const locked = readOnly || disabled;
  return (
    <section className={`practice-editor${disabled ? ' is-disabled' : ''}`} aria-label="Code editor">
      <header className="practice-editor__toolbar">
        <span className="practice-editor__label">Solution</span>
        <span className="practice-editor__language">Python</span>
        <span className="practice-editor__key-help" id={descriptionId}>Tab indents · Esc then Tab moves focus</span>
      </header>
      <div className="practice-editor__mount" ref={editorHostRef} />
      {locked && (
        <span className="practice-editor__note">
          {readOnly ? readOnlyMessage : 'The editor is unavailable.'}
        </span>
      )}
    </section>
  );
}
