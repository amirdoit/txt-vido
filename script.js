document.addEventListener('DOMContentLoaded', () => {
    const videoForm = document.getElementById('videoForm');
    const videoOutput = document.getElementById('videoOutput');
    const videoTextInput = document.getElementById('videoText');
    const backgroundColorInput = document.getElementById('backgroundColor');
    const submitButton = videoForm.querySelector('button[type="submit"]');

    videoForm.addEventListener('submit', function(event) {
        event.preventDefault(); 

        const videoText = videoTextInput.value;
        const backgroundColor = backgroundColorInput.value;

        generateVideo(videoText, backgroundColor); 
    });

    function generateVideo(text, bgColor) {
        console.log(`Generating video with text: "${text}" and background: ${bgColor}`);
        videoOutput.innerHTML = ''; 
        videoOutput.style.backgroundColor = bgColor;
        const textElement = document.createElement('p');
        textElement.textContent = text;
        textElement.style.color = isLightColor(bgColor) ? 'black' : 'white';
        textElement.style.textAlign = 'center';
        textElement.style.fontSize = '24px';
        textElement.style.padding = '20px';
        videoOutput.appendChild(textElement);
    }

    function isLightColor(hexColor) {
        // Ensure hexColor is a string and has a valid format
        if (typeof hexColor !== 'string' || !/^#[0-9A-F]{6}$/i.test(hexColor)) {
            console.error("Invalid hexColor format in isLightColor:", hexColor);
            return false; // Default to dark or handle error appropriately
        }
        let r = parseInt(hexColor.slice(1, 3), 16);
        let g = parseInt(hexColor.slice(3, 5), 16);
        let b = parseInt(hexColor.slice(5, 7), 16);
        let luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
        return luminance > 0.5;
    }

    // Basic Test Function
    function runBasicTest() {
        console.log("Running basic test...");
        const testText = "Test Video Text";
        const testBgColor = "#123456"; // A dark color

        // Set form values
        videoTextInput.value = testText;
        backgroundColorInput.value = testBgColor;

        // Simulate form submission
        submitButton.click();

        // Check results (with a slight delay to allow DOM update)
        setTimeout(() => {
            const outputP = videoOutput.querySelector('p');
            // Browsers convert hex to rgb for style.backgroundColor
            const expectedRgbBgColor = "rgb(18, 52, 86)"; 
            const actualBgColor = videoOutput.style.backgroundColor;
            
            const expectedTextColor = isLightColor(testBgColor) ? 'black' : 'white';
            const actualTextColor = outputP ? outputP.style.color : null;

            if (actualBgColor === expectedRgbBgColor &&
                outputP && outputP.textContent === testText &&
                actualTextColor === expectedTextColor) {
                console.log("Basic test PASSED!");
            } else {
                console.error("Basic test FAILED!");
                console.error("Expected background:", expectedRgbBgColor, "Got:", actualBgColor);
                console.error("Expected text content:", testText, "Got:", outputP ? outputP.textContent : 'null');
                console.error("Expected text color:", expectedTextColor, "Got:", actualTextColor);
            }
        }, 100); // 100ms delay
    }

    // Run the test automatically after everything is set up
    runBasicTest(); 
});
