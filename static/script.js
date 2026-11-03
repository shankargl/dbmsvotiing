
document.addEventListener("DOMContentLoaded", function () {

    // Vote submission confirmation
    const votingForm = document.getElementById("votingForm");

    if (votingForm) {
        votingForm.addEventListener("submit", function (event) {

            const selectedCandidate =
                document.querySelector(
                    'input[name="candidate_id"]:checked'
                );

            if (!selectedCandidate) {
                event.preventDefault();
                alert("Please select a candidate before voting.");
                return;
            }

            const confirmation = confirm(
                "Are you sure you want to submit your vote?\n\n" +
                "You cannot change your vote after submission."
            );

            if (!confirmation) {
                event.preventDefault();
            }
        });
    }


    // Automatically hide flash messages
    const flashMessages =
        document.querySelectorAll(".flash");

    flashMessages.forEach(function (message) {

        setTimeout(function () {

            message.style.transition = "opacity 0.5s ease";
            message.style.opacity = "0";

            setTimeout(function () {
                message.remove();
            }, 500);

        }, 4000);

    });


    // Candidate selection effect
    const candidateCards =
        document.querySelectorAll(".candidate-card");

    candidateCards.forEach(function (card) {

        card.addEventListener("click", function () {

            candidateCards.forEach(function (item) {
                item.classList.remove("selected");
            });

            card.classList.add("selected");

        });

    });

});
