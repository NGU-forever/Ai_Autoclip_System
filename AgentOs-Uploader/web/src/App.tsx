import { Routes, Route } from 'react-router-dom';
import { VideoDistributor } from './pages/VideoDistributor';

export default function App() {
  return (
    <Routes>
      <Route index element={<VideoDistributor />} />
      <Route path="*" element={<VideoDistributor />} />
    </Routes>
  );
}
