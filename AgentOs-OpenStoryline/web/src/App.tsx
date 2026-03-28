import { Routes, Route } from 'react-router-dom';
import { LegacyOpenStoryline } from './LegacyOpenStoryline';
import { OpenStorylineShell } from './OpenStorylineShell';

export default function App() {
  return (
    <OpenStorylineShell>
      <Routes>
        <Route index element={<LegacyOpenStoryline />} />
        <Route path="*" element={<LegacyOpenStoryline />} />
      </Routes>
    </OpenStorylineShell>
  );
}
