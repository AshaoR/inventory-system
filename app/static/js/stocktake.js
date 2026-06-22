document.querySelectorAll('.actual-input').forEach(function(input) {
    input.addEventListener('input', function() {
        var row = this.closest('tr');
        var bookQty = parseFloat(row.querySelector('.book-qty').textContent) || 0;
        var actualQty = parseFloat(this.value) || 0;
        var diffCell = row.querySelector('.diff-cell');
        var diff = actualQty - bookQty;
        diffCell.textContent = diff;
        diffCell.style.color = diff > 0 ? '#52c41a' : diff < 0 ? '#ff4d4f' : 'inherit';
    });
});
