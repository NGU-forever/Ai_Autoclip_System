import { Routes, Route } from 'react-router-dom';
import { LegacyOpenStoryline } from './LegacyOpenStoryline';

export default function App() {
  return (
    <Routes>
      <Route index element={<LegacyOpenStoryline />} />
      <Route path="*" element={<LegacyOpenStoryline />} />
    </Routes>
  );
}
