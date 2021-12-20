#define CLASS(T, body) typedef struct body T;
struct Vector3 {
    int x;
    int y;
    int z;
};

CLASS(Node, {
    long long left;
    int right;
})

typedef struct Vector3 Vector3;

int gMyX = 5;
extern int gMyY;

int test(long long *param, Vector3* y) {
    Vector3 v = {5, 17, 0};
    *param = 4.5f;
    return v.x;
}

int(*testptr)(long long *, Vector3*);

void testn(int (*test)(long long *, Vector3*));

Vector3* test2(int n, Vector3* v3);

//void myfunc(char* x, char** y, const char* z, Vector3 *v4) {}