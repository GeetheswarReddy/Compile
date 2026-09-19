import React, { useEffect, useId, useRef, useState } from 'react';
import { apiClient } from '../api/client';
import RecordingConsent from './RecordingConsent';
import './reflection.css';

const DEFAULT_TYPE = 'audio/webm';

function supportedType() {
  if (typeof MediaRecorder === 'undefined') return '';
  return ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4'].find((type) => MediaRecorder.isTypeSupported?.(type)) || DEFAULT_TYPE;
}

function expiryLabel(value) {
  if (!value) return 'expires after 30 days';
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? 'expires after 30 days' : `expires ${date.toLocaleDateString()}`;
}

/**
 * Private single-recording card.
 * Props: questionId (required), optional reflection metadata, onSaved(record), onDeleted().
 */
export default function ReflectionCard({ questionId, reflection = null, onSaved, onDeleted, disabled = false }) {
  const titleId = useId();
  const [record, setRecord] = useState(reflection);
  const [consentOpen, setConsentOpen] = useState(false);
  const [replacing, setReplacing] = useState(false);
  const [status, setStatus] = useState('idle');
  const [error, setError] = useState('');
  const recorderRef = useRef(null);
  const chunksRef = useRef([]);
  const streamRef = useRef(null);

  useEffect(() => {
    if (!questionId) return;
    const controller = new AbortController();
    apiClient.getReflection(questionId, { signal: controller.signal })
      .then((payload) => setRecord(payload.reflection))
      .catch((error) => { if (error.name !== 'AbortError') setError(error.message); });
    return () => controller.abort();
  }, [questionId]);
  useEffect(() => () => {
    if (recorderRef.current) { recorderRef.current.onstop = null; if (recorderRef.current.state === "recording") recorderRef.current.stop(); }
    streamRef.current?.getTracks().forEach((track) => track.stop());
  }, []);

  const startRecording = async () => {
    setConsentOpen(false);
    setError('');
    try {
      if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') throw new Error('Audio recording is not supported in this browser.');
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = supportedType();
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      chunksRef.current = [];
      streamRef.current = stream;
      recorderRef.current = recorder;
      recorder.ondataavailable = (event) => event.data.size && chunksRef.current.push(event.data);
      recorder.onstop = async () => {
        stream.getTracks().forEach((track) => track.stop());
        const type = recorder.mimeType || mimeType || DEFAULT_TYPE;
        const blob = new Blob(chunksRef.current, { type });
        if (!blob.size) { setStatus('idle'); setError('No audio was captured.'); return; }
        setStatus('saving');
        try {
          const payload = await apiClient.createReflection({ questionId, contentType: type, ...(replacing ? { confirmReplacement: true } : {}) });
          if (!payload?.uploadUrl) throw new Error('The recording upload URL was not returned.');
          const upload = await fetch(payload.uploadUrl, { method: 'PUT', headers: { 'Content-Type': payload.contentType || type }, body: blob });
          if (!upload.ok) throw new Error('The recording could not be uploaded.');
          const playback = await apiClient.getReflection(questionId);
          const saved = { ...playback.reflection, questionId, contentType: payload.contentType || type };
          setRecord(saved); setStatus('saved'); setReplacing(false); onSaved?.(saved);
        } catch (requestError) { setStatus('idle'); setError(requestError?.message || 'The reflection could not be saved.'); }
      };
      recorder.start();
      setStatus('recording');
    } catch (requestError) { setStatus('idle'); setError(requestError?.message || 'Microphone access was not granted.'); }
  };

  const stopRecording = () => recorderRef.current?.state === 'recording' && recorderRef.current.stop();
  const deleteRecording = async () => {
    if (!questionId || status === 'deleting') return;
    setStatus('deleting'); setError('');
    try { await apiClient.deleteReflection(questionId); setRecord(null); setStatus('idle'); onDeleted?.(); }
    catch (requestError) { setStatus('saved'); setError(requestError?.message || 'The reflection could not be deleted.'); }
  };

  const hasRecord = Boolean(record);
  return (
    <section className="reflection-card" aria-labelledby={titleId}>
      <div className="reflection-card__header">
        <div><p className="reflection-eyebrow">Private reflection</p><h2 id={titleId}>Capture what you learned</h2></div>
        <span className="reflection-lock" aria-label="Private recording">Private</span>
      </div>
      <p className="reflection-card__intro">Talk through your approach, what changed, or what you want to remember.</p>
      <p className="reflection-card__privacy">Your recording is private, {hasRecord ? expiryLabel(record.expiresAt) : 'and any recording expires after 30 days'}.</p>
      {error && <p className="reflection-error" role="alert">{error}</p>}
      {status === 'recording' && <p className="reflection-status" role="status">Recording… press stop when you are finished.</p>}
      {status === 'saving' && <p className="reflection-status" role="status">Saving your reflection…</p>}
      {status === 'saved' && <p className="reflection-status" role="status">Reflection saved.</p>}
      {record?.playbackUrl && <audio controls src={record.playbackUrl} aria-label="Play your reflection" />}
      <div className="reflection-actions">
        {status === 'recording' ? <button className="reflection-button reflection-button--primary" type="button" onClick={stopRecording}>Stop recording</button> : <button className="reflection-button reflection-button--primary" type="button" onClick={() => { setReplacing(hasRecord); setConsentOpen(true); }} disabled={disabled || status === 'saving' || status === 'deleting'}>{hasRecord ? 'Record a replacement' : 'Record reflection'}</button>}
        {hasRecord && <button className="reflection-button reflection-button--danger" type="button" onClick={deleteRecording} disabled={disabled || status === 'deleting' || status === 'saving'}>{status === 'deleting' ? 'Deleting…' : 'Delete recording'}</button>}
      </div>
      <RecordingConsent open={consentOpen} replacing={replacing} onConfirm={startRecording} onCancel={() => { setConsentOpen(false); setReplacing(false); }} />
    </section>
  );
}
