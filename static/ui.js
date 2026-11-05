
/* =====================================================
   CIPHERART UI INTERACTIONS
   UI ONLY - DOES NOT MODIFY BACKEND OPERATIONS
===================================================== */

document.addEventListener("DOMContentLoaded", function () {

    // 1. Image preview untuk upload
    const artworkInput = document.getElementById("image");
    const artworkPreview = document.getElementById("imagePreview");
    const previewArea = document.getElementById("previewArea");
    const fileName = document.getElementById("fileName");

    if (artworkInput && artworkPreview) {
        artworkInput.addEventListener("change", function () {

            const file = this.files[0];

            if (!file) {
                if (previewArea) {
                    previewArea.style.display = "none";
                }
                return;
            }

            if (!file.type.startsWith("image/")) {
                alert("Please select an image.");
                this.value = "";
                return;
            }

            artworkPreview.src = URL.createObjectURL(file);

            if (fileName) {
                fileName.textContent = file.name;
            }

            if (previewArea) {
                previewArea.style.display = "block";
            }
        });
    }

    // 2. Search/filter gallery visual
    const searchInput = document.getElementById("gallerySearch");
    const cards = document.querySelectorAll(".kartu");

    if (searchInput) {
        searchInput.addEventListener("input", function () {

            const keyword = this.value.toLowerCase();

            cards.forEach(function (card) {

                const content = card.textContent.toLowerCase();

                card.style.display = content.includes(keyword)
                    ? ""
                    : "none";

            });

        });
    }

    // 3. Preview watermark image
    const watermarkInput = document.getElementById("image");
    const watermarkArea = document.getElementById("wmPreview");
    const watermarkImage = document.getElementById("wmImage");

    if (
        watermarkInput &&
        watermarkArea &&
        watermarkImage &&
        !artworkPreview
    ) {
        watermarkInput.addEventListener("change", function () {

            const file = this.files[0];

            if (!file) {
                watermarkArea.style.display = "none";
                return;
            }

            watermarkImage.src = URL.createObjectURL(file);
            watermarkArea.style.display = "block";

        });
    }

    // 4. File input visual feedback
    document.querySelectorAll('input[type="file"]').forEach(function (input) {

        input.addEventListener("change", function () {

            if (!this.files.length) return;

            this.classList.add("file-selected");

        });

    });

});
