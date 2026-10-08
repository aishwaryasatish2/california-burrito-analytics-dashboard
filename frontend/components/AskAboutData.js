"use client";

import { useState } from "react";

import { QUESTIONS } from "@/lib/questions";

// A fixed list of questions, not a chat box: there is no free-text input.
export default function AskAboutData({ data }) {
  const [selectedId, setSelectedId] = useState(QUESTIONS[0].id);
  const question = QUESTIONS.find((q) => q.id === selectedId);
  const result = question.answer(data);

  return (
    <div className="grid-2">
      <section className="panel" aria-labelledby="ask-title">
        <h2 id="ask-title">Ask About Your Data</h2>
        <p className="panel-caption">Choose a question. Answers use the dashboard&apos;s current filters.</p>

        <div className="question-list" role="radiogroup" aria-labelledby="ask-title">
          {QUESTIONS.map((q) => (
            <label key={q.id} className={`question${q.id === selectedId ? " is-selected" : ""}`}>
              <input type="radio" name="question" checked={q.id === selectedId}
                     onChange={() => setSelectedId(q.id)} />
              {q.label}
            </label>
          ))}
        </div>

        <div aria-live="polite">
          <h3 className="answer-title">{question.label}</h3>
          {result.empty ? <p className="muted">{result.empty}</p> : <AnswerTable result={result} />}
        </div>
      </section>

      <section className="panel" aria-labelledby="insights-title">
        <h2 id="insights-title">Insights &amp; Opportunities</h2>
        <div className="insights-box" aria-live="polite">
          {result.empty ? (
            <p className="muted">There is no result to interpret for this selection.</p>
          ) : (
            <>
              <h3>What the data shows</h3>
              <ul>{result.findings.map((text, i) => <li key={i}>{text}</li>)}</ul>
              {result.gaps.length > 0 && (
                <>
                  <h3>Gaps worth a closer look</h3>
                  <ul>{result.gaps.map((text, i) => <li key={i}>{text}</li>)}</ul>
                </>
              )}
            </>
          )}
          <p className="chart-note">
            These are comparisons within the current selection. They show where the numbers differ, not why.
          </p>
        </div>
      </section>
    </div>
  );
}

function AnswerTable({ result }) {
  return (
    <div className="table-scroll">
      <table className="data-table">
        <thead>
          <tr>
            {result.columns.map((label, i) => (
              <th key={label} scope="col" className={i > 0 ? "num" : undefined}>{label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {result.rows.map((row) => (
            <tr key={row[0]}>
              {row.map((cell, i) =>
                i === 0 ? <th key={i} scope="row">{cell}</th> : <td key={i} className="num">{cell}</td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
