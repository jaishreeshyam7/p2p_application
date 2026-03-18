import { useState, useCallback } from 'react';
import webgazer from 'webgazer';

export const useEyeTracking = () => {
  const [isLookingAway, setIsLookingAway] = useState(false);

  const initEyeTracking = useCallback(async () => {
    try {
      await webgazer.setGazeListener((data, elapsedTime) => {
        if (data == null) return;

        const screenWidth = window.innerWidth;
        const screenHeight = window.innerHeight;

        // Define a "safe zone" (center 60% of the screen)
        const safeZoneXMin = screenWidth * 0.2;
        const safeZoneXMax = screenWidth * 0.8;
        const safeZoneYMin = screenHeight * 0.1;
        const safeZoneYMax = screenHeight * 0.9;

        if (
          data.x < safeZoneXMin || 
          data.x > safeZoneXMax || 
          data.y < safeZoneYMin || 
          data.y > safeZoneYMax
        ) {
          setIsLookingAway(true);
        } else {
          setIsLookingAway(false);
        }
      }).begin();

      webgazer.showVideoPreview(false);
      webgazer.showPredictionPoints(false); 
      
    } catch (error) {
      console.error("WebGazer failed to start:", error);
    }
  }, []);

  const stopEyeTracking = useCallback(() => {
    if (window.webgazer) {
      window.webgazer.pause();
      window.webgazer.end();
    }
    setIsLookingAway(false);
  }, []);

  // Return the state and functions so App.js can use them
  return { isLookingAway, initEyeTracking, stopEyeTracking };
};