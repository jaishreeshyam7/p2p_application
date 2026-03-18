import React from 'react';

const MetricBar = ({ label, value, max, color }) => (
  <div className="mb-2">
    <div className="flex justify-between text-xs mb-1">
      <span className="text-gray-400">{label}</span>
      <span className="text-gray-300 font-mono">{value}{max ? `/${max}` : ''}</span>
    </div>
    <div className="h-1.5 bg-gray-700 rounded-full overflow-hidden">
      <div 
        className={`h-full ${color} rounded-full transition-all duration-500`} 
        style={{ width: `${max ? (value/max)*100 : value}%` }} 
      />
    </div>
  </div>
);

export default MetricBar;