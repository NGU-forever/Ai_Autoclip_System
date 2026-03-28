import { Routes, Route } from 'react-router-dom';
import { VideoDistributor } from './pages/VideoDistributor';

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<VideoDistributor />} />
      <Route path="*" element={<VideoDistributor />} />
    </Routes>
  );
}
