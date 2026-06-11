// Stocktake: auto-calculate difference on input
document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('.actual-input').forEach(function(input) {
        input.addEventListener('input', function() {
            var row = this.closest('tr');
            var bookQty = parseFloat(row.querySelector('.book-qty').textContent) || 0;
            var actualQty = parseFloat(this.value) || 0;
            var diffCell = row.querySelector('.diff-cell');
            var diff = actualQty - bookQty;
            diffCell.textContent = diff;
            diffCell.className = 'diff-cell' + (diff > 0 ? ' text-success fw-bold' : diff < 0 ? ' text-danger fw-bold' : '');
        });
    });
});
